"""P7.S1.M03 — recursive PIT and forbidden-field firewall."""

from __future__ import annotations

from copy import deepcopy

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact
from ..errors import P7S1Error
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from .common import nonfinite_paths, parse_aware_datetime, walk_json

MODULE_ID = "P7.S1.M03"
DEFAULT_FORBIDDEN_FIELDS = (
    "future_return",
    "realized_outcome",
    "realized_pnl",
    "portfolio_weight",
    "final_position_size",
    "execution_price",
    "rank",
    "candidate_score",
)
MODEL_TIME_FIELDS = ("model_trained_at", "forecast_created_at")
RUNTIME_TIME_FIELDS = (
    "decision_time",
    "available_at",
    "market_snapshot_time",
    "quote_time",
    "forecast_created_at",
    "model_trained_at",
)


class FirewallPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    forbidden_fields: tuple[str, ...] = DEFAULT_FORBIDDEN_FIELDS
    runtime_time_fields: tuple[str, ...] = RUNTIME_TIME_FIELDS


def execute(bundle_payload: dict[str, JsonValue], config_payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    config, policy, bundle = _parse_inputs(bundle_payload, config_payload)
    before_snapshot = deepcopy(bundle.model_dump(mode="python"))
    copied_records = deepcopy(list(bundle.records))
    scan = _scan_records(copied_records, policy, config.context.decision_time)
    _raise_scan_violations(scan)
    _verify_immutability(bundle, before_snapshot)
    return _build_outputs(config, policy, copied_records)


def _parse_inputs(bundle_payload, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        policy = FirewallPolicy.model_validate(config.policy)
        bundle = ArtifactEnvelope.model_validate(bundle_payload)
    except ValidationError as exc:
        raise P7S1Error(
            ReasonCode.P6_SCHEMA_INCOMPATIBLE,
            "candidate bundle or firewall configuration is invalid",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    if bundle.artifact_name != "validated_strategy_candidate_bundle":
        raise P7S1Error(
            ReasonCode.P6_SCHEMA_INCOMPATIBLE,
            "M03 requires validated_strategy_candidate_bundle",
            MODULE_ID,
        )
    if bundle.decision_time != config.context.decision_time:
        raise P7S1Error(
            ReasonCode.P6_CLOCK_MISMATCH,
            "candidate bundle decision_time differs from module context",
            MODULE_ID,
        )
    return config, policy, bundle


def _scan_records(records, policy, decision_time):
    forbidden = set(policy.forbidden_fields)
    result = {"forbidden": [], "temporal": [], "nonfinite": []}
    for index, record in enumerate(records):
        prefix = f"$.records[{index}]"
        result["nonfinite"].extend(f"{prefix}{path[1:]}" for path in nonfinite_paths(record))
        for path, value in walk_json(record):
            field_name = path.rsplit(".", maxsplit=1)[-1]
            if "[" in field_name:
                continue
            if field_name.lower() in forbidden:
                result["forbidden"].append({"path": f"{prefix}{path[1:]}", "field": field_name})
            if field_name in policy.runtime_time_fields:
                hit = _time_violation(path, field_name, value, decision_time)
                if hit is not None:
                    hit["path"] = f"{prefix}{path[1:]}"
                    result["temporal"].append(hit)
    return result


def _time_violation(path, field_name, value, decision_time):
    try:
        timestamp = parse_aware_datetime(value)
    except ValueError as exc:
        raise P7S1Error(
            ReasonCode.NAIVE_TIMESTAMP,
            "runtime timestamp is not timezone-aware",
            MODULE_ID,
            {"path": path, "field": field_name},
        ) from exc
    except (TypeError, OverflowError) as exc:
        raise P7S1Error(
            ReasonCode.P6_SCHEMA_INCOMPATIBLE,
            "runtime timestamp cannot be parsed",
            MODULE_ID,
            {"path": path, "field": field_name},
        ) from exc
    if field_name == "decision_time" and timestamp != decision_time:
        return {
            "path": path,
            "field": field_name,
            "timestamp": timestamp.isoformat(),
            "decision_time": decision_time.isoformat(),
        }
    if timestamp <= decision_time:
        return None
    return {
        "path": path,
        "field": field_name,
        "timestamp": timestamp.isoformat(),
        "decision_time": decision_time.isoformat(),
    }


def _raise_scan_violations(scan) -> None:
    if scan["nonfinite"]:
        raise P7S1Error(
            ReasonCode.NONFINITE_WIRE_VALUE,
            "candidate bundle contains NaN or Infinity",
            MODULE_ID,
            {"paths": scan["nonfinite"][:50]},
        )
    if scan["forbidden"]:
        raise P7S1Error(
            ReasonCode.FORBIDDEN_FIELD,
            "candidate bundle contains forbidden future or portfolio fields",
            MODULE_ID,
            {"hits": scan["forbidden"][:50], "hit_count": len(scan["forbidden"])},
        )
    if scan["temporal"]:
        model_hit = any(hit["field"] in MODEL_TIME_FIELDS for hit in scan["temporal"])
        reason = ReasonCode.MODEL_AFTER_DECISION if model_hit else ReasonCode.FUTURE_INFORMATION
        raise P7S1Error(
            reason,
            "candidate bundle contains runtime information after decision_time",
            MODULE_ID,
            {"hits": scan["temporal"][:50], "hit_count": len(scan["temporal"])},
        )


def _verify_immutability(bundle, before_snapshot) -> None:
    after_snapshot = bundle.model_dump(mode="python")
    if before_snapshot != after_snapshot:
        raise P7S1Error(
            ReasonCode.INPUT_MUTATION_DETECTED,
            "input candidate bundle changed during firewall execution",
            MODULE_ID,
        )


def _build_outputs(config, policy, records):
    safe = create_artifact(
        artifact_name="temporally_safe_candidate_bundle",
        records=records,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
    )
    temporal_report = create_artifact(
        artifact_name="temporal_integrity_report",
        records=[
            {
                "status": "PASS",
                "candidate_count": len(records),
                "checked_runtime_time_fields": list(policy.runtime_time_fields),
                "violation_count": 0,
            }
        ],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_firewall_run",
    )
    forbidden_report = create_artifact(
        artifact_name="forbidden_field_report",
        records=[],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_forbidden_field_hit",
    )
    return {
        "temporally_safe_candidate_bundle": safe.model_dump(mode="json"),
        "temporal_integrity_report": temporal_report.model_dump(mode="json"),
        "forbidden_field_report": forbidden_report.model_dump(mode="json"),
    }
