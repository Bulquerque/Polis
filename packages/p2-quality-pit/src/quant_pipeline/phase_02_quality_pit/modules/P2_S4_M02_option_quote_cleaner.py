from __future__ import annotations

from collections import defaultdict
from typing import Any

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import iso_date, parse_datetime
from ._s2_temporal import parse_as_of_cutoff
from ._s4_option_helpers import (
    combine_quality_status,
    contract_indexes,
    is_quote_candidate,
    normalize_option_type,
    optional_number,
    quote_age_seconds,
    resolve_quote_contract,
    source_quality_for,
    option_source_allowed,
)


def _date_or_none(row: dict[str, Any]) -> str | None:
    for field in ("date", "as_of_date", "available_at", "declared_available_at"):
        if row.get(field) not in (None, ""):
            try:
                return iso_date(row.get(field), field=field)
            except ContractValidationError:
                continue
    return None


def _validate_future(row: dict[str, Any], config: dict) -> None:
    cutoff = config.get("as_of_date")
    available = row.get("available_at") or row.get("declared_available_at")
    if cutoff in (None, "") or available in (None, ""):
        return
    parsed_cutoff = parse_as_of_cutoff(cutoff, config)
    if parsed_cutoff is not None and parse_datetime(available, field="available_at") > parsed_cutoff:
        raise ContractValidationError("no_future_availability violation")


def _normalize_quote(row: dict[str, Any], contract: dict[str, Any], match_mode: str, source_quality_panel: Any, config: dict) -> dict[str, Any]:
    _validate_future(row, config)
    source_status, source_reasons = source_quality_for(row, source_quality_panel)

    date_value = _date_or_none(row)
    expiration = contract.get("expiration_date") or row.get("expiration_date")
    if date_value and expiration and date_value > str(expiration):
        raise ContractValidationError("quote_after_expiration")
    first_seen = contract.get("first_seen_date")
    last_seen = contract.get("last_seen_date")
    if date_value and first_seen and date_value < first_seen:
        raise ContractValidationError("quote_before_contract_first_seen")
    if date_value and last_seen and date_value > last_seen:
        raise ContractValidationError("quote_after_contract_last_seen")

    bid = optional_number(row.get("bid"), field="bid", nonnegative=True)
    ask = optional_number(row.get("ask"), field="ask", nonnegative=True)
    last_price = optional_number(
        row.get("last_price") if row.get("last_price") not in (None, "") else row.get("last"),
        field="last_price",
        nonnegative=True,
    )
    volume = optional_number(row.get("volume"), field="volume", nonnegative=True)
    financial_volume = optional_number(row.get("financial_volume"), field="financial_volume", nonnegative=True)
    open_interest = optional_number(row.get("open_interest"), field="open_interest", nonnegative=True)

    reasons = list(source_reasons)
    if bid is None:
        reasons.append("MISSING_BID")
    if ask is None:
        reasons.append("MISSING_ASK")
    if last_price is None:
        reasons.append("MISSING_LAST_PRICE")
    if bid is not None and ask is not None and bid > ask:
        raise ContractValidationError("CROSSED_MARKET")

    is_indicative = bid is None or ask is None

    feed_type = row.get("feed_type") or row.get("feed")
    if str(feed_type or "").strip().upper() in {"INDICATIVE", "DELAYED", "MODIFIED"}:
        reasons.append("NON_PRIMARY_FEED")

    quote_age = quote_age_seconds(row.get("available_at"), row.get("as_of_date") or config.get("as_of_date"))
    max_age = config.get("max_quote_age_seconds")
    if quote_age is not None and max_age not in (None, "") and quote_age > float(max_age):
        reasons.append("STALE_QUOTE")

    quality_flag = combine_quality_status(reasons, source_status)
    return {
        "date": date_value,
        "as_of_date": row.get("as_of_date") or date_value,
        "available_at": row.get("available_at") or row.get("declared_available_at"),
        "underlying": contract.get("underlying") or row.get("underlying") or "UNKNOWN",
        "option_id": contract.get("option_id") or row.get("option_id") or "UNKNOWN",
        "expiration_date": contract.get("expiration_date") or row.get("expiration_date"),
        "contract_key": contract.get("contract_key"),
        "option_type": contract.get("option_type") or normalize_option_type(row.get("option_type")),
        "strike": contract.get("strike") if contract.get("strike") is not None else optional_number(row.get("strike"), field="strike", positive=True),
        "last_price": last_price,
        "indicative_proxy": last_price if is_indicative else None,
        "proxy_method": "last_price" if is_indicative and last_price is not None else None,
        "execution_status": "NON_EXECUTABLE" if is_indicative else "EXECUTABLE",
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "financial_volume": financial_volume,
        "open_interest": open_interest,
        "source_id": row.get("source_id") or contract.get("source_id") or "UNKNOWN",
        "lineage_id": row.get("lineage_id") or contract.get("lineage_id") or "UNKNOWN",
        "quality_flag": quality_flag,
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        "match_mode": match_mode,
        "quality_reasons": sorted(set(reasons)),
        "source_observation_key": row.get("contract_key"),
        "feed_type": feed_type,
        "provider": row.get("provider"),
        "source_hash": row.get("source_hash") or row.get("raw_content_sha256"),
        "observed_at": row.get("observed_at"),
        "quote_age_seconds": quote_age,
        "greeks_source": row.get("greeks_source"),
        "greeks_timestamp": row.get("greeks_timestamp"),
        **{field: row.get(field) for field in ("iv", "delta", "gamma", "theta", "vega", "rho") if field in row},
    }


def _select_for_grain(rows: list[dict[str, Any]], config: dict) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("date"), row.get("contract_key"))].append(row)

    selected: list[dict[str, Any]] = []
    source_priority = {str(source): idx for idx, source in enumerate(config.get("source_priority", []))}
    for _, group in sorted(groups.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        def key(row: dict[str, Any]) -> tuple[str, int, str]:
            available = str(row.get("available_at") or "")
            source = str(row.get("source_id") or "")
            # Latest causally available quote first; provider priority breaks ties.
            return available, -source_priority.get(source, len(source_priority) + 1), source

        selected.append(sorted(group, key=key)[-1])
    return selected


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "clean_option_contract_panel", "source_quality_panel"]
    require_inputs(inputs, required)

    contracts = records(inputs[required[1]], required[1])
    indexes = contract_indexes(contracts)
    source_rows = records(inputs[required[0]], required[0])
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []

    for row in source_rows:
        if not is_quote_candidate(row):
            continue
        if not option_source_allowed(row, config):
            continue
        try:
            contract, match_mode = resolve_quote_contract(row, indexes)
            if contract is None:
                rejected.append("quote_contract_not_found")
                continue
            accepted.append(_normalize_quote(row, contract, match_mode, inputs["source_quality_panel"], config))
        except ContractValidationError as exc:
            rejected.append(str(exc))
            continue

    quotes = _select_for_grain(accepted, config)
    no_forbidden_rows(quotes)
    output = artifact(
        "clean-option-quotes-panel",
        quotes,
        config,
        quote_has_contract_key=all(row.get("contract_key") in indexes["by_key"] for row in quotes),
        no_score=True,
        input_count=len(source_rows),
        accepted_count=len(quotes),
        rejected_count=len(rejected),
        rejection_reasons=sorted(set(rejected)),
        indicative_only_count=sum(1 for row in quotes if row.get("execution_status") == "NON_EXECUTABLE"),
        executable_quote_count=sum(1 for row in quotes if row.get("execution_status") == "EXECUTABLE"),
    )
    return {
        "module_id": "P2.S4.M02",
        "module_name": "option_quote_cleaner",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S4",
        "contract": "P2_S4_M02_option_quote_cleaner.yaml",
        "required_inputs": required,
        "outputs": {"clean_option_quotes_panel": output},
    }
