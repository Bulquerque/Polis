from __future__ import annotations

from collections import defaultdict
from typing import Any

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import iso_date, row_date
from ._s4_option_helpers import (
    DOMAIN_OPTION_QUOTE,
    canonical_contract_key,
    choose_primary,
    explicit_option_domain,
    contract_calendar_status,
    is_option_candidate,
    normalize_expiration,
    normalize_option_type,
    optional_number,
    source_quality_for,
    option_source_allowed,
)


def _observed_date(row: dict[str, Any]) -> str | None:
    for field in ("first_seen_date", "date", "available_at", "declared_available_at"):
        if row.get(field) not in (None, ""):
            try:
                return iso_date(row.get(field), field=field)
            except ContractValidationError:
                continue
    return None


def _last_seen_date(row: dict[str, Any], first_seen: str | None) -> str | None:
    del first_seen
    value = row.get("last_seen_date")
    if value in (None, ""):
        return None
    return iso_date(value, field="last_seen_date")


def _normalize_contract(row: dict[str, Any], calendar_panel: Any, source_quality_panel: Any, config: dict) -> dict[str, Any]:
    option_id = str(row.get("option_id") or "").strip()
    if not option_id:
        raise ContractValidationError("option_id is required")

    expiration = normalize_expiration(row)
    strike = optional_number(row.get("strike"), field="strike", positive=True)
    if strike is None:
        raise ContractValidationError("strike is required")

    option_type = normalize_option_type(row.get("option_type") or row.get("call_put") or row.get("right"))
    contract_size = optional_number(
        row.get("contract_size") if row.get("contract_size") not in (None, "") else row.get("multiplier"),
        field="contract_size",
        positive=True,
    )
    source_status, source_reasons = source_quality_for(row, source_quality_panel)
    canonical_key, identity_mode, identity_reasons = canonical_contract_key(row)
    # Preserve the upstream/public contract_key when present for drop-in compatibility.
    # canonical_contract_key is the authoritative economic identity used for
    # deduplication and quote resolution across providers.
    public_key = str(row.get("contract_key")) if row.get("contract_key") not in (None, "") else canonical_key
    first_seen = _observed_date(row)
    last_seen = _last_seen_date(row, first_seen)
    if first_seen and last_seen and last_seen < first_seen:
        raise ContractValidationError("first_seen_date must be <= last_seen_date")

    calendar_status, calendar_row = contract_calendar_status(row, calendar_panel)
    reasons = [*source_reasons, *identity_reasons]
    if option_type == "UNKNOWN":
        reasons.append("OPTION_TYPE_UNKNOWN")
    if contract_size is None:
        reasons.append("CONTRACT_SIZE_UNKNOWN")
    if calendar_status == "UNKNOWN":
        reasons.append("EXPIRATION_CALENDAR_UNKNOWN")

    return {
        "option_id": option_id,
        "expiration_date": expiration,
        "contract_key": public_key,
        "canonical_contract_key": str(row.get("canonical_contract_key") or canonical_key),
        "underlying": row.get("underlying") or "UNKNOWN",
        "option_type": option_type,
        "strike": strike,
        "contract_size": contract_size,
        "first_seen_date": first_seen,
        "last_seen_date": last_seen,
        "expiration_calendar_date": expiration,
        "source_id": row.get("source_id") or "UNKNOWN",
        "lineage_id": row.get("lineage_id") or "UNKNOWN",
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        "source_observation_key": row.get("contract_key"),
        "identity_mode": identity_mode,
        "calendar_status": calendar_status,
        "calendar_id": (calendar_row or {}).get("calendar_id"),
        "source_quality_status": source_status,
        "quality_reasons": sorted(set(reasons)),
        "provider": row.get("provider"),
        "feed_type": row.get("feed_type") or row.get("feed"),
        "adjustment_code": row.get("adjustment_code") or row.get("deliverable_id"),
    }


def _merge_contract_group(group: list[dict[str, Any]], config: dict) -> dict[str, Any]:
    if len(group) == 1:
        return group[0]

    core_fields = ("underlying", "expiration_date", "option_type", "strike")
    reference = group[0]
    for candidate in group[1:]:
        for field in core_fields:
            left = reference.get(field)
            right = candidate.get(field)
            if left not in (None, "UNKNOWN") and right not in (None, "UNKNOWN") and left != right:
                raise ContractValidationError(f"option_contract_provider_conflict: {field}")
        left_size = reference.get("contract_size")
        right_size = candidate.get("contract_size")
        if left_size is not None and right_size is not None and left_size != right_size:
            raise ContractValidationError("option_contract_provider_conflict: contract_size")

    primary = dict(choose_primary(group, config.get("source_priority")))
    primary["provider_option_ids"] = sorted({str(row.get("option_id")) for row in group if row.get("option_id")})
    primary["source_ids"] = sorted({str(row.get("source_id")) for row in group if row.get("source_id")})
    all_reasons = {reason for row in group for reason in row.get("quality_reasons", [])}
    primary["quality_reasons"] = sorted(all_reasons)
    return primary


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "clean_calendar_panel", "source_quality_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected: list[str] = []

    deferred_quotes: list[dict[str, Any]] = []
    for row in source_rows:
        if not is_option_candidate(row):
            continue
        if not option_source_allowed(row, config):
            continue
        if explicit_option_domain(row) == DOMAIN_OPTION_QUOTE:
            deferred_quotes.append(row)
            continue
        try:
            normalized = _normalize_contract(row, inputs["clean_calendar_panel"], inputs["source_quality_panel"], config)
        except ContractValidationError as exc:
            rejected.append(str(exc))
            continue
        groups[normalized["canonical_contract_key"]].append(normalized)

    # Some providers expose only option-chain/quote rows. Derive a contract from
    # such a row only when the same canonical contract was not already supplied
    # by an explicit contract record. This prevents quote-level missing metadata
    # from degrading a richer contract definition.
    for row in deferred_quotes:
        if not option_source_allowed(row, config):
            continue
        try:
            normalized = _normalize_contract(row, inputs["clean_calendar_panel"], inputs["source_quality_panel"], config)
        except ContractValidationError as exc:
            rejected.append(str(exc))
            continue
        if normalized["canonical_contract_key"] not in groups:
            groups[normalized["canonical_contract_key"]].append(normalized)

    contracts = [_merge_contract_group(group, config) for _, group in sorted(groups.items())]
    no_forbidden_rows(contracts)

    output = artifact(
        "clean-option-contract-panel",
        contracts,
        config,
        option_id_present=all(row.get("option_id") not in (None, "") for row in contracts),
        expiration_date_present=all(row.get("expiration_date") not in (None, "") for row in contracts),
        strike_present=all(row.get("strike") is not None for row in contracts),
        contract_key_present=all(row.get("contract_key") not in (None, "") for row in contracts),
        canonical_contract_key_present=all(row.get("canonical_contract_key") not in (None, "") for row in contracts),
        input_count=len(source_rows),
        accepted_count=len(contracts),
        rejected_count=len(rejected),
        rejection_reasons=sorted(set(rejected)),
        contract_key_version="option_contract_key.v1",
    )
    return {
        "module_id": "P2.S4.M01",
        "module_name": "option_contract_parser",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S4",
        "contract": "P2_S4_M01_option_contract_parser.yaml",
        "required_inputs": required,
        "outputs": {"clean_option_contract_panel": output},
    }
