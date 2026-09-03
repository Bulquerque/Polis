from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..models import CompatibilityMode, ExecutionContext
from ..runtime.canonical import deterministic_id
from ..runtime.schema_validation import validate_json_schema
from .errors import TemporalContractError, TemporalErrorCode
from .output import build_s2_artifact
from .policy import policy_for
from .time import optional_instant


def _records(artifact: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    rows = artifact.get("records", [])
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise TemporalContractError(
            TemporalErrorCode.INPUT_INVALID,
            "records must be a list of mappings",
            path=f"{name}.records",
        )
    return rows


def _explicit_entity(payload: Mapping[str, Any]) -> str | None:
    for field in ("entity_id", "underlying_id", "underlying", "canonical_instrument_id"):
        if payload.get(field) not in (None, ""):
            return str(payload[field])
    return None


def _entity_id(record: Mapping[str, Any], context: ExecutionContext) -> tuple[str, str, str]:
    artifact_name = str(record["source_artifact_name"])
    payload = record["payload"]
    if not isinstance(payload, Mapping):
        raise TemporalContractError(
            TemporalErrorCode.INPUT_INVALID,
            "payload must be a mapping",
            path=f"{artifact_name}.payload",
        )
    policy = policy_for(artifact_name)
    explicit = _explicit_entity(payload)
    if explicit:
        return explicit, policy.entity_type, "EXPLICIT_CANONICAL_ID"
    for field in policy.identity_fields:
        value = payload.get(field)
        if value in (None, ""):
            continue
        prefix = {
            "MACRO_SERIES": "macro",
            "BENCHMARK": "benchmark",
            "CALENDAR": "calendar",
            "EVENT": "event",
            "DOCUMENT": "document",
            "SOURCE": "source",
            "CURVE": "curve",
            "INSTRUMENT": "instrument",
        }.get(policy.entity_type, policy.entity_type.lower())
        return f"{prefix}:{value}", policy.entity_type, f"NAMESPACED_{field.upper()}"
    fallback_fields = {
        "clean_option_contract_panel": ("contract_key", "option_id"),
        "clean_option_quotes_panel": ("contract_key", "option_id"),
        "clean_liquidity_reference_panel": ("contract_key", "option_id"),
        "clean_calendar_panel": ("calendar_id", "venue", "exchange"),
    }.get(artifact_name, ())
    for field in fallback_fields:
        if payload.get(field) not in (None, ""):
            return f"{policy.entity_type.lower()}:{payload[field]}", policy.entity_type, "DEGRADED_FALLBACK"
    if artifact_name == "clean_calendar_panel" and context.compatibility_mode is CompatibilityMode.RC4_1:
        return "calendar:GLOBAL", "CALENDAR", "DEGRADED_GLOBAL_CALENDAR"
    raise TemporalContractError(
        TemporalErrorCode.ENTITY_UNRESOLVED,
        "no canonical entity field is available",
        path=f"{artifact_name}.records[{record['source_record_index']}]",
    )


def _date_text(record: Mapping[str, Any]) -> str | None:
    payload = record.get("payload", {})
    if isinstance(payload, Mapping):
        for field in ("session_date", "date", "effective_date", "ex_date", "reference_date"):
            value = payload.get(field)
            if value not in (None, ""):
                return str(value)[:10]
    for field in ("reference_time", "event_time"):
        value = record.get(field)
        if value:
            return str(value)[:10]
    return None


def _calendar_id(payload: Mapping[str, Any]) -> str | None:
    for field in ("calendar_id", "venue", "exchange"):
        if payload.get(field) not in (None, ""):
            return str(payload[field])
    return None


def _calendar_index(records: list[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in records:
        if record.get("source_artifact_name") != "clean_calendar_panel":
            continue
        payload = record.get("payload", {})
        if not isinstance(payload, Mapping):
            continue
        calendar = _calendar_id(payload) or "GLOBAL"
        date_value = _date_text(record)
        if not date_value:
            continue
        key = (calendar, date_value)
        previous = result.get(key)
        if previous is not None and previous.get("payload") != payload:
            raise TemporalContractError(
                TemporalErrorCode.INPUT_INVALID,
                f"conflicting calendar rows for {key}",
                path="clean_calendar_panel",
            )
        result[key] = record
    return result


def _corporate_action_index(
    records: list[Mapping[str, Any]], context: ExecutionContext
) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records:
        if record.get("source_artifact_name") != "clean_corporate_actions_panel":
            continue
        entity_id, _, _ = _entity_id(record, context)
        payload = record.get("payload", {})
        if not isinstance(payload, Mapping):
            continue
        timezone_name = str(payload.get("timezone") or payload.get("source_timezone") or "UTC")
        announcement = optional_instant(
            payload.get("announcement_time") or payload.get("announced_at") or payload.get("published_at"),
            path="corporate_action.announcement_time",
            timezone_name=timezone_name,
            date_only_policy="start_of_day",
        )
        effective = optional_instant(
            payload.get("effective_time") or payload.get("effective_date") or payload.get("ex_date"),
            path="corporate_action.effective_time",
            timezone_name=timezone_name,
            date_only_policy="start_of_day",
        )
        if announcement and effective and announcement.value > effective.value:
            raise TemporalContractError(
                TemporalErrorCode.CORPORATE_ACTION_ORDER_INVALID,
                "announcement_time must not follow effective_time",
                path=f"clean_corporate_actions_panel.records[{record['source_record_index']}]",
            )
        effective_date = effective.utc_text()[:10] if effective else _date_text(record)
        if effective_date:
            action_id = str(payload.get("action_id") or record["source_record_id"])
            result[(entity_id, effective_date)].append(action_id)
    return {key: sorted(set(values)) for key, values in result.items()}



def _validated_records(
    inputs: Mapping[str, Any], input_schema: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    name = "temporally_resolved_observation_bundle"
    if name not in inputs:
        raise TemporalContractError(
            TemporalErrorCode.INPUT_MISSING,
            f"{name} is required",
            path="inputs",
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
    return _records(bundle, name)


def _matching_calendar(
    record: Mapping[str, Any],
    calendar_index: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[str | None, Mapping[str, Any] | None]:
    payload = record.get("payload", {})
    assert isinstance(payload, Mapping)
    date_value = _date_text(record)
    if not date_value:
        return None, None
    calendar_id = _calendar_id(payload)
    calendar_row = calendar_index.get((calendar_id, date_value)) if calendar_id else None
    return calendar_id, calendar_row or calendar_index.get(("GLOBAL", date_value))


def _alignment_status(
    entity_type: str,
    resolution: str,
    date_value: str | None,
    calendar_row: Mapping[str, Any] | None,
    existing_warnings: list[str],
) -> tuple[str, list[str]]:
    status = "ALIGNED"
    warnings = list(existing_warnings)
    if resolution.startswith("DEGRADED"):
        status = "DEGRADED"
        warnings.append(f"entity resolution used {resolution}")
    if date_value and calendar_row is None and entity_type in {"UNDERLYING", "BENCHMARK"}:
        status = "DEGRADED"
        warnings.append("no calendar row matched the observation date")
    return status, warnings


def _align_record(
    record: Mapping[str, Any],
    context: ExecutionContext,
    calendar_index: Mapping[tuple[str, str], Mapping[str, Any]],
    action_index: Mapping[tuple[str, str], list[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    entity_id, entity_type, resolution = _entity_id(record, context)
    date_value = _date_text(record)
    calendar_id, calendar_row = _matching_calendar(record, calendar_index)
    calendar_payload = calendar_row.get("payload", {}) if calendar_row else {}
    actions = action_index.get((entity_id, date_value or ""), [])
    status, warnings = _alignment_status(
        entity_type,
        resolution,
        date_value,
        calendar_row,
        list(record.get("warnings", [])),
    )
    aligned = {
        **dict(record),
        "entity_id": entity_id,
        "entity_type": entity_type,
        "entity_resolution": resolution,
        "calendar_id": calendar_id or ("GLOBAL" if calendar_row else None),
        "session_date": date_value,
        "is_trading_day": calendar_payload.get("is_trading_day"),
        "session_open": calendar_payload.get("session_open"),
        "session_close": calendar_payload.get("session_close"),
        "corporate_action_ids": actions,
        "alignment_status": status,
        "warnings": warnings,
    }
    report = {
        "source_record_id": record["source_record_id"],
        "entity_id": entity_id,
        "entity_type": entity_type,
        "resolution": resolution,
        "calendar_id": aligned["calendar_id"],
        "session_date": date_value,
        "status": status,
        "warnings": warnings,
    }
    return aligned, report


def _aligned_records(
    source_records: list[Mapping[str, Any]], context: ExecutionContext
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    calendars = _calendar_index(source_records)
    actions = _corporate_action_index(source_records, context)
    aligned: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for record in source_records:
        aligned_record, report_record = _align_record(
            record, context, calendars, actions
        )
        aligned.append(aligned_record)
        report.append(report_record)
    aligned.sort(
        key=lambda row: (row["entity_id"], row["available_at"], row["source_record_id"])
    )
    report.sort(key=lambda row: (row["entity_id"], row["source_record_id"]))
    return aligned, report


def align_entities_and_calendars(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
    *,
    input_schema: Mapping[str, Any],
    s2_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    source_records = _validated_records(inputs, input_schema)
    aligned, report = _aligned_records(source_records, context)
    output = build_s2_artifact(
        name="entity_aligned_observation_bundle",
        module_id="P4.S2.M02",
        context=context,
        records=aligned,
        schema=s2_schemas["entity_aligned_observation_bundle"],
        extra={"entity_policy_version": "p4.s2.entity.v1"},
    )
    alignment_report = build_s2_artifact(
        name="entity_alignment_report",
        module_id="P4.S2.M02",
        context=context,
        records=report,
        schema=s2_schemas["entity_alignment_report"],
    )
    return {
        "entity_aligned_observation_bundle": output,
        "entity_alignment_report": alignment_report,
    }
