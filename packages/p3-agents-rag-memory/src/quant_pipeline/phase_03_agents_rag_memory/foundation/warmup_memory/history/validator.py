from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .errors import ValidationIssue, WarmupHistoryValidationError
from .models import (
    DatasetPartition,
    EvaluationWindowConfig,
    HistoryRecord,
    OutputLineage,
    Phase3RunSnapshotView,
    ValidatedWarmupHistory,
    ValidationIssueModel,
    ValidationStatus,
    ValidationSummary,
    WarmupHistoryBundle,
    WarmupMode,
)

LOGGER = logging.getLogger(__name__)
MODULE_ID = "P3.S9.M01"
FORBIDDEN_FIELDS = {
    "target",
    "future_return",
    "label",
    "prediction",
    "candidate_id",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "realized_pnl",
    "buy_sell_signal",
}

EventSink = Callable[[dict[str, object]], None]


def _emit(sink: EventSink | None, event: str, **dimensions: object) -> None:
    payload = {"event": event, "module_id": MODULE_ID, **dimensions}
    LOGGER.info(event, extra={"p3": payload})
    if sink is not None:
        sink(payload)


def _scan_forbidden_fields(value: object, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                raise WarmupHistoryValidationError(
                    [
                        ValidationIssue(
                            code="P3_S9_M01_FORBIDDEN_FIELD",
                            message=f"Forbidden field '{key_text}' is not allowed in P3.S9.",
                            path=f"{path}.{key_text}",
                        )
                    ]
                )
            _scan_forbidden_fields(child, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _scan_forbidden_fields(child, f"{path}[{index}]")


def _normalize_snapshot(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    nested = normalized.get("evaluation_window")
    if isinstance(nested, Mapping):
        normalized.setdefault("evaluation_start", nested.get("start"))
        normalized.setdefault("evaluation_end", nested.get("end"))
    if "items" in normalized and isinstance(normalized["items"], list):
        for item in normalized["items"]:
            if not isinstance(item, Mapping):
                continue
            key = item.get("key") or item.get("name")
            value = item.get("value")
            if key in {"run_id", "snapshot_id", "as_of", "as_of_time", "evaluation_start", "evaluation_end", "lineage_id", "snapshot_hash"}:
                normalized.setdefault(str(key), value)
    return normalized


def _normalize_evaluation_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    normalized.setdefault("schema_id", "evaluation_window_config.s9.v1")
    normalized.setdefault("schema_version", "1.0.0")
    normalized.setdefault("warmup_end_strictly_before_evaluation", True)
    normalized.setdefault("final_holdout_blind", True)
    normalized.setdefault("timezone", "UTC")
    normalized.setdefault("boundary_rule", "available_at_equal_as_of_allowed")
    return normalized


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _model_json(model: object) -> object:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", by_alias=True, exclude_none=True)
    return model


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _artifact_id(run_id: str, history_hash: str) -> str:
    return f"p3-s9-{run_id}-{history_hash[:16]}"


def _record_sort_key(record: HistoryRecord) -> tuple[str, str, str, str]:
    return (
        record.available_at.isoformat(),
        record.event_time.isoformat(),
        record.event_id,
        record.history_record_id,
    )


def _resolve_evaluation_start(
    snapshot: Phase3RunSnapshotView,
    config: EvaluationWindowConfig,
) -> datetime:
    evaluation_start = config.evaluation_start or snapshot.evaluation_start
    if evaluation_start is None:
        raise WarmupHistoryValidationError(
            [
                ValidationIssue(
                    code="P3_S9_M01_EVALUATION_START_MISSING",
                    message="evaluation_start must be declared by the run snapshot or evaluation config.",
                    path="evaluation_window_config.evaluation_start",
                )
            ]
        )
    return evaluation_start.astimezone(UTC)


def _validate_record_set(
    bundle: WarmupHistoryBundle,
    snapshot: Phase3RunSnapshotView,
    config: EvaluationWindowConfig,
    evaluation_start: datetime,
) -> tuple[HistoryRecord, ...]:
    issues: list[ValidationIssue] = []
    if len(bundle.records) > config.max_records:
        issues.append(
            ValidationIssue(
                code="P3_S9_M01_RECORD_LIMIT_EXCEEDED",
                message=f"History has {len(bundle.records)} records; limit is {config.max_records}.",
                path="warmup_history_bundle.records",
            )
        )

    holdout_ids = set(config.holdout_artifact_ids)
    allowed_partitions = set(config.allowed_partitions)
    forbidden_partitions = set(config.forbidden_partitions)
    seen_record_ids: set[str] = set()
    seen_event_payloads: set[tuple[str, str]] = set()

    for index, record in enumerate(bundle.records):
        base = f"warmup_history_bundle.records[{index}]"
        if record.history_record_id in seen_record_ids:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_DUPLICATE_HISTORY_RECORD_ID",
                    message=f"Duplicate history_record_id: {record.history_record_id}",
                    path=f"{base}.history_record_id",
                )
            )
        seen_record_ids.add(record.history_record_id)

        event_payload_key = (record.event_id, record.payload_ref.content_hash)
        if event_payload_key in seen_event_payloads:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_DUPLICATE_EVENT_PAYLOAD",
                    message="The same event and payload hash appears more than once.",
                    path=base,
                )
            )
        seen_event_payloads.add(event_payload_key)

        if record.partition in forbidden_partitions or record.partition not in allowed_partitions:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_HOLDOUT_OR_FORBIDDEN_PARTITION",
                    message=f"Partition {record.partition.value} is not allowed in warm-up.",
                    path=f"{base}.partition",
                )
            )

        record_ids = {
            record.history_record_id,
            record.event_id,
            record.source_id,
            record.payload_ref.artifact_id,
            *record.lineage.source_artifact_ids,
            *record.lineage.holdout_refs,
        }
        intersection = holdout_ids & record_ids
        if record.lineage.holdout_refs or intersection:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_HOLDOUT_LEAKAGE",
                    message="Record or lineage references a declared holdout artifact.",
                    path=f"{base}.lineage",
                    details={"matched_ids": sorted(intersection | set(record.lineage.holdout_refs))},
                )
            )

        if config.warmup_start and record.available_at < config.warmup_start:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_BEFORE_WARMUP_WINDOW",
                    message="Record was available before the configured warm-up start.",
                    path=f"{base}.available_at",
                )
            )

        if config.warmup_end_strictly_before_evaluation:
            if record.available_at >= evaluation_start:
                issues.append(
                    ValidationIssue(
                        code="P3_S9_M01_EVALUATION_OVERLAP",
                        message="Warm-up record was available at or after evaluation_start.",
                        path=f"{base}.available_at",
                        details={
                            "available_at": record.available_at.isoformat(),
                            "evaluation_start": evaluation_start.isoformat(),
                        },
                    )
                )
        elif record.available_at > evaluation_start:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_EVALUATION_OVERLAP",
                    message="Warm-up record was available after evaluation_start.",
                    path=f"{base}.available_at",
                )
            )

        if config.boundary_rule == "available_at_equal_as_of_allowed":
            violates_as_of = record.available_at > snapshot.as_of
        else:
            violates_as_of = record.available_at >= snapshot.as_of
        if violates_as_of:
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_AVAILABLE_AT_AFTER_AS_OF",
                    message="Record was not available under the run snapshot as_of boundary.",
                    path=f"{base}.available_at",
                    details={
                        "available_at": record.available_at.isoformat(),
                        "as_of": snapshot.as_of.isoformat(),
                    },
                )
            )

        if config.holdout_start and config.holdout_end:
            if config.holdout_start <= record.available_at < config.holdout_end:
                issues.append(
                    ValidationIssue(
                        code="P3_S9_M01_HOLDOUT_WINDOW_OVERLAP",
                        message="Record availability falls inside the holdout window.",
                        path=f"{base}.available_at",
                    )
                )

        if record.payload_ref.artifact_id not in set(record.lineage.source_artifact_ids):
            issues.append(
                ValidationIssue(
                    code="P3_S9_M01_LINEAGE_PAYLOAD_REF_MISSING",
                    message="payload_ref.artifact_id must appear in lineage.source_artifact_ids.",
                    path=f"{base}.lineage.source_artifact_ids",
                )
            )

    if issues:
        raise WarmupHistoryValidationError(issues)
    return tuple(sorted(bundle.records, key=_record_sort_key))


def validate_warmup_history(
    *,
    warmup_history_bundle: Mapping[str, Any],
    phase3_run_snapshot: Mapping[str, Any],
    evaluation_window_config: Mapping[str, Any],
    event_sink: EventSink | None = None,
) -> ValidatedWarmupHistory:
    started = perf_counter()
    run_id = str(phase3_run_snapshot.get("run_id", "unknown"))
    _emit(event_sink, "module_started", run_id=run_id)

    try:
        _scan_forbidden_fields(
            {
                "warmup_history_bundle": warmup_history_bundle,
                "phase3_run_snapshot": phase3_run_snapshot,
                "evaluation_window_config": evaluation_window_config,
            }
        )
        try:
            bundle = WarmupHistoryBundle.model_validate(warmup_history_bundle)
            snapshot = Phase3RunSnapshotView.model_validate(_normalize_snapshot(phase3_run_snapshot))
            config = EvaluationWindowConfig.model_validate(_normalize_evaluation_config(evaluation_window_config))
        except ValidationError as exc:
            issues = [
                ValidationIssue(
                    code="P3_S9_M01_INPUT_INVALID",
                    message=error["msg"],
                    path=".".join(str(item) for item in error["loc"]),
                    details={"type": error["type"]},
                )
                for error in exc.errors(include_url=False, include_input=False)
            ]
            raise WarmupHistoryValidationError(issues) from exc

        _emit(event_sink, "input_contract_validated", run_id=snapshot.run_id)
        evaluation_start = _resolve_evaluation_start(snapshot, config)
        records = _validate_record_set(bundle, snapshot, config, evaluation_start)

        normalized_history = {
            "schema_id": bundle.schema_id,
            "schema_version": bundle.schema_version,
            "history_id": bundle.history_id,
            "mode": bundle.mode.value,
            "records": [_model_json(record) for record in records],
            "lineage_id": bundle.lineage_id,
            "source_bundle_refs": [
                _model_json(ref)
                for ref in sorted(bundle.source_bundle_refs, key=lambda item: item.artifact_id)
            ],
        }
        input_history_hash = _sha256(normalized_history)
        history_hash = _sha256(
            {
                "history_id": bundle.history_id,
                "mode": bundle.mode.value,
                "records": [_model_json(record) for record in records],
                "lineage_id": bundle.lineage_id,
            }
        )
        source_artifact_ids = tuple(
            sorted(
                {
                    artifact_id
                    for record in records
                    for artifact_id in record.lineage.source_artifact_ids
                }
                | {ref.artifact_id for ref in bundle.source_bundle_refs}
            )
        )
        source_lineage_ids = tuple(
            sorted({bundle.lineage_id, *(record.lineage.lineage_id for record in records)})
        )

        info_issues: tuple[ValidationIssueModel, ...] = ()
        if bundle.mode is WarmupMode.GENESIS_ONLY:
            info_issues = (
                ValidationIssueModel(
                    code="P3_S9_M01_NO_APPROVED_WARMUP_HISTORY",
                    severity="INFO",
                    message="Genesis mode selected; no historical records will be replayed.",
                    path="warmup_history_bundle.mode",
                ),
            )

        earliest = min((record.available_at for record in records), default=None)
        latest = max((record.available_at for record in records), default=None)
        result = ValidatedWarmupHistory(
            artifact_id=_artifact_id(snapshot.run_id, history_hash),
            run_id=snapshot.run_id,
            snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of,
            mode=bundle.mode,
            status=ValidationStatus.READY,
            evaluation_start=evaluation_start,
            warmup_start=config.warmup_start or earliest,
            warmup_end=latest,
            records=records,
            history_hash=history_hash,
            lineage=OutputLineage(
                lineage_id=f"{bundle.lineage_id}:validated:{history_hash[:12]}",
                input_history_id=bundle.history_id,
                input_history_hash=input_history_hash,
                input_snapshot_id=snapshot.snapshot_id,
                input_snapshot_hash=snapshot.snapshot_hash,
                source_artifact_ids=source_artifact_ids,
                source_lineage_ids=source_lineage_ids,
            ),
            validation_summary=ValidationSummary(
                input_record_count=len(bundle.records),
                output_record_count=len(records),
                unique_event_count=len({record.event_id for record in records}),
                unique_source_count=len({record.source_id for record in records}),
                earliest_available_at=earliest,
                latest_available_at=latest,
            ),
            issues=info_issues,
        )
        _emit(
            event_sink,
            "module_succeeded",
            run_id=snapshot.run_id,
            input_record_count=len(bundle.records),
            output_record_count=len(records),
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        return result
    except WarmupHistoryValidationError as exc:
        _emit(
            event_sink,
            "module_failed",
            run_id=run_id,
            error_count=len(exc.issues),
            error_codes=[issue.code for issue in exc.issues],
            duration_ms=round((perf_counter() - started) * 1000, 3),
        )
        raise
