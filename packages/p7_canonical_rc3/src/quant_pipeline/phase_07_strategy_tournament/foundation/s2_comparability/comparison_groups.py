"""P7.S2.M02 — deterministic economic comparison groups and query IDs."""

from __future__ import annotations

from collections import Counter
import re

from pydantic import JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact, verify_artifact_hash
from ..canonical import content_sha256
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from ..s2_errors import P7S2Error
from .common import finite_number, first_path, get_path
from .models import ComparisonGroupPolicy, ComparisonGroupPolicyRegistry, ComparisonGroupRecord

MODULE_ID = "P7.S2.M02"


def execute(
    eligible_payload: dict[str, JsonValue],
    registry_payload: dict[str, JsonValue],
    config_payload: dict[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    before = content_sha256({"eligible": eligible_payload, "registry": registry_payload})
    config, eligible, policy = _parse_inputs(eligible_payload, registry_payload, config_payload)
    provisional = [_build_record(record, policy) for record in eligible.records]
    counts = Counter(str(item["comparison_group_id"]) for item in provisional)
    records = [
        ComparisonGroupRecord.model_validate({**item, "group_size": counts[str(item["comparison_group_id"])]}).model_dump(mode="json")
        for item in provisional
    ]
    records.sort(key=lambda item: str(item["candidate_id"]))
    outputs = _build_outputs(config, policy, records, counts)
    after = content_sha256({"eligible": eligible_payload, "registry": registry_payload})
    if before != after:
        raise P7S2Error(
            ReasonCode.S2_INPUT_MUTATION_DETECTED,
            "comparison grouping mutated its inputs",
            MODULE_ID,
        )
    return outputs


def _parse_inputs(eligible_payload, registry_payload, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        eligible = ArtifactEnvelope.model_validate(eligible_payload)
        registry = ComparisonGroupPolicyRegistry.model_validate(registry_payload)
    except ValidationError as exc:
        raise P7S2Error(
            ReasonCode.COMPARISON_GROUP_POLICY_INVALID,
            "comparison group inputs or registry failed validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    if eligible.artifact_name != "eligible_strategy_candidate_panel" or not verify_artifact_hash(eligible):
        raise P7S2Error(
            ReasonCode.S2_INPUT_INVALID,
            "eligible candidate panel is invalid or has a mismatched hash",
            MODULE_ID,
        )
    return config, eligible, registry.active()


def _build_record(record: dict[str, JsonValue], policy: ComparisonGroupPolicy) -> dict[str, JsonValue]:
    candidate_id = _required_string(record, "candidate_id")
    cycle_id = _required_string(record, "cycle_id")
    decision_time = _required_string(record, "decision_time")
    underlying_id = _required_string(record, "underlying_id")
    horizon = _required_string(record, "horizon")
    objective = _required_string(record, "objective_family")
    supported = horizon in policy.supported_horizons
    structured = policy.allow_structured_horizons and bool(
        re.fullmatch(r"[1-9]\d*_calendar_days", horizon)
    )
    if policy.supported_horizons and not supported and not structured:
        raise P7S2Error(
            ReasonCode.HORIZON_UNSUPPORTED,
            "eligible candidate has a horizon outside the comparison policy",
            MODULE_ID,
            {"candidate_id": candidate_id, "horizon": horizon},
        )
    risk_path, capital_at_risk = _resolve_capital_at_risk(record, policy)
    bucket = _resolve_bucket(capital_at_risk, policy)
    currency = _resolve_currency(record, policy)
    key = {
        "cycle_id": cycle_id,
        "decision_time": decision_time,
        "underlying_id": underlying_id,
        "horizon": horizon,
        "objective_family": objective,
        "capital_at_risk_bucket": bucket,
        "currency": currency,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
    }
    group_id = f"cmp-{content_sha256(key)}"
    return {
        "candidate_id": candidate_id,
        "comparison_group_id": group_id,
        "query_id": group_id,
        "cycle_id": cycle_id,
        "decision_time": decision_time,
        "underlying_id": underlying_id,
        "horizon": horizon,
        "objective_family": objective,
        "capital_at_risk": capital_at_risk,
        "capital_at_risk_source": risk_path,
        "capital_at_risk_bucket": bucket,
        "currency": currency,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
    }


def _required_string(record: dict[str, JsonValue], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise P7S2Error(
            ReasonCode.COMPARISON_KEY_MISSING,
            "eligible candidate is missing a comparison key",
            MODULE_ID,
            {"candidate_id": record.get("candidate_id"), "key": key},
        )
    return value


def _resolve_capital_at_risk(record, policy) -> tuple[str, float]:
    resolved = first_path(record, policy.capital_at_risk_sources)
    if resolved is None:
        raise P7S2Error(
            ReasonCode.CAPITAL_RISK_BUCKET_UNRESOLVED,
            "no configured capital-at-risk source is available",
            MODULE_ID,
            {"candidate_id": record.get("candidate_id")},
        )
    path, raw = resolved
    numeric = finite_number(raw)
    if numeric is None or numeric < 0:
        raise P7S2Error(
            ReasonCode.CAPITAL_RISK_BUCKET_UNRESOLVED,
            "capital at risk must be a finite non-negative number",
            MODULE_ID,
            {"candidate_id": record.get("candidate_id"), "path": path, "value": raw},
        )
    return path, numeric


def _resolve_bucket(value: float, policy: ComparisonGroupPolicy) -> str:
    for bucket in policy.risk_buckets:
        if value < bucket.lower_inclusive:
            continue
        if bucket.upper_exclusive is None or value < bucket.upper_exclusive:
            return bucket.bucket_id
    raise P7S2Error(
        ReasonCode.CAPITAL_RISK_BUCKET_UNRESOLVED,
        "capital at risk did not fit any configured bucket",
        MODULE_ID,
        {"value": value},
    )


def _resolve_currency(record, policy) -> str:
    resolved = first_path(record, policy.currency_sources)
    if resolved is None or not isinstance(resolved[1], str) or not resolved[1]:
        raise P7S2Error(
            ReasonCode.CURRENCY_SCOPE_MISMATCH,
            "currency is missing from every configured source",
            MODULE_ID,
            {"candidate_id": record.get("candidate_id")},
        )
    values = {
        str(get_path(record, path))
        for path in policy.currency_sources
        if get_path(record, path, None) is not None
    }
    if len(values) > 1:
        raise P7S2Error(
            ReasonCode.CURRENCY_SCOPE_MISMATCH,
            "candidate currency sources disagree",
            MODULE_ID,
            {"candidate_id": record.get("candidate_id"), "currencies": sorted(values)},
        )
    return str(resolved[1])


def _build_outputs(config, policy, records, counts):
    groups = create_artifact(
        artifact_name="candidate_comparison_group_panel",
        records=records,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
    )
    sizes = sorted(counts.values())
    audit = create_artifact(
        artifact_name="comparison_group_audit",
        records=[
            {
                "status": "PASS",
                "policy_id": policy.policy_id,
                "policy_version": policy.version,
                "candidate_count": len(records),
                "comparison_group_count": len(counts),
                "singleton_group_count": sum(size == 1 for size in sizes),
                "minimum_group_size": min(sizes) if sizes else 0,
                "maximum_group_size": max(sizes) if sizes else 0,
            }
        ],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_grouping_run",
    )
    return {
        "candidate_comparison_group_panel": groups.model_dump(mode="json"),
        "comparison_group_audit": audit.model_dump(mode="json"),
    }
