from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from ..models import ExecutionContext
from ..runtime.canonical import canonical_json, deterministic_id
from ..runtime.schema_validation import validate_json_schema
from .errors import TemporalContractError, TemporalErrorCode
from .output import build_s2_artifact
from .policy import policy_for

_RESERVED = {
    "artifact_id", "created_at", "lineage_id", "pipeline_version", "run_id",
    "cycle_id", "as_of_time", "available_at", "ingested_at", "event_time",
    "reference_time", "published_at", "publication_time", "date", "as_of_date",
    "source_id", "timezone", "source_timezone", "entity_id", "underlying_id",
    "underlying", "canonical_instrument_id",
}


def _typed_value(value: Any) -> dict[str, Any]:
    result = {
        "value_type": "NULL",
        "value_number": None,
        "value_integer": None,
        "value_boolean": None,
        "value_string": None,
        "value_json": None,
    }
    if value is None:
        return result
    if isinstance(value, bool):
        result.update(value_type="BOOLEAN", value_boolean=value)
    elif isinstance(value, int):
        result.update(value_type="INTEGER", value_integer=value)
    elif isinstance(value, float):
        if not isfinite(value):
            raise TemporalContractError(
                TemporalErrorCode.NON_FINITE_VALUE,
                "non-finite numeric values are forbidden",
            )
        result.update(value_type="NUMBER", value_number=value)
    elif isinstance(value, str):
        result.update(value_type="STRING", value_string=value)
    elif isinstance(value, (list, dict)):
        result.update(value_type="JSON", value_json=canonical_json(value))
    else:
        result.update(value_type="STRING", value_string=str(value))
    return result


def _dimensions(payload: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        field: payload[field]
        for field in fields
        if payload.get(field) not in (None, "")
    }


def _value_fields(artifact_name: str, payload: Mapping[str, Any]) -> list[str]:
    policy = policy_for(artifact_name)
    fields = list(policy.required_value_fields)
    fields.extend(
        field
        for field in policy.optional_value_fields
        if field not in fields and field in payload
    )
    if fields:
        return fields
    return sorted(
        field
        for field, value in payload.items()
        if field not in _RESERVED and isinstance(value, (str, int, float, bool))
    )


def _validate_input(
    inputs: Mapping[str, Any], input_schema: Mapping[str, Any]
) -> Mapping[str, Any]:
    name = "quality_enriched_observation_bundle"
    if name not in inputs:
        raise TemporalContractError(
            TemporalErrorCode.INPUT_MISSING, f"{name} is required", path="inputs"
        )
    bundle = inputs[name]
    if not isinstance(bundle, Mapping):
        raise TemporalContractError(
            TemporalErrorCode.INPUT_INVALID, "bundle must be a mapping"
        )
    try:
        validate_json_schema(bundle, input_schema, name)
    except Exception as exc:
        raise TemporalContractError(
            TemporalErrorCode.SCHEMA_INVALID, str(exc), path=name
        ) from exc
    return bundle


def _eligible(source: Mapping[str, Any]) -> bool:
    blocked = {"QUALITY_BLOCKED", "REVISED_SUPERSEDED"}
    return bool(source.get("selected_vintage")) and source.get("missingness_state") not in blocked


def _canonical_row(
    source: Mapping[str, Any],
    field: str,
    value: Any,
    dimensions: Mapping[str, Any],
) -> dict[str, Any]:
    variable_id = f"{str(source['source_modality']).lower()}.{field}"
    identity = {
        "source_record_id": source["source_record_id"],
        "variable_id": variable_id,
        "decision_time": source["decision_time"],
    }
    missingness = str(source.get("missingness_state") or "OBSERVED")
    if value is None:
        missingness = "STRUCTURALLY_MISSING"
    return {
        "observation_id": deterministic_id("observation", identity, 28),
        "decision_time": source["decision_time"],
        "entity_id": source["entity_id"],
        "entity_type": source["entity_type"],
        "variable_id": variable_id,
        **_typed_value(value),
        "source_modality": source["source_modality"],
        "source_artifact_name": source["source_artifact_name"],
        "source_artifact_id": source["source_artifact_id"],
        "source_record_id": source["source_record_id"],
        "event_time": source.get("event_time"),
        "reference_time": source.get("reference_time"),
        "published_at": source.get("published_at"),
        "available_at": source["available_at"],
        "ingested_at": source.get("ingested_at"),
        "calendar_id": source.get("calendar_id"),
        "session_date": source.get("session_date"),
        "quality_state": source.get("quality_state"),
        "missingness_state": missingness,
        "freshness_seconds": source.get("freshness_seconds"),
        "vintage_id": source.get("vintage_id"),
        "dimensions": dict(dimensions),
        "source_lineage_id": source["source_lineage_id"],
    }


def _canonical_rows(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    observation_ids: set[str] = set()
    for source in records:
        if not _eligible(source):
            continue
        payload = source.get("payload", {})
        if not isinstance(payload, Mapping):
            continue
        policy = policy_for(str(source["source_artifact_name"]))
        dimensions = _dimensions(payload, policy.dimension_fields)
        for field in _value_fields(policy.artifact_name, payload):
            row = _canonical_row(source, field, payload.get(field), dimensions)
            observation_id = row["observation_id"]
            if observation_id in observation_ids:
                raise TemporalContractError(
                    TemporalErrorCode.CANONICAL_DUPLICATE,
                    f"duplicate canonical observation {observation_id}",
                    path="canonical_observation_panel",
                )
            observation_ids.add(observation_id)
            canonical.append(row)
    canonical.sort(
        key=lambda row: (
            row["decision_time"],
            row["entity_id"],
            row["variable_id"],
            row["source_record_id"],
        )
    )
    return canonical


def _store_manifest_record(panel: Mapping[str, Any], fingerprint: str) -> dict[str, Any]:
    return {
        "artifact_name": "canonical_observation_panel",
        "artifact_id": panel["artifact_id"],
        "content_hash": panel["content_hash"],
        "semantic_fingerprint": fingerprint,
        "row_count": len(panel["records"]),
        "grain": panel["grain"],
        "partition_keys": ["decision_date", "source_modality", "entity_bucket"],
        "storage_format_recommendation": "PARQUET_DATASET",
    }


def build_canonical_store(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    input_schema: Mapping[str, Any],
    s2_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    bundle = _validate_input(inputs, input_schema)
    records = bundle.get("records", [])
    assert isinstance(records, list)
    canonical = _canonical_rows(records)
    fingerprint = deterministic_id("semantic", canonical, 40)
    panel = build_s2_artifact(
        name="canonical_observation_panel",
        module_id="P4.S2.M04",
        context=context,
        records=canonical,
        schema=s2_schemas["canonical_observation_panel"],
        extra={
            "grain": ["decision_time", "entity_id", "variable_id", "source_record_id"],
            "semantic_fingerprint": fingerprint,
        },
    )
    manifest = build_s2_artifact(
        name="canonical_store_manifest",
        module_id="P4.S2.M04",
        context=context,
        records=[_store_manifest_record(panel, fingerprint)],
        schema=s2_schemas["canonical_store_manifest"],
    )
    return {
        "canonical_observation_panel": panel,
        "canonical_store_manifest": manifest,
    }
