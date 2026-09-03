from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any, Iterable

from .economic_models import (
    AtomicFeaturePanel,
    AtomicFeatureRecord,
    ExecutionContext,
    ExecutionStatus,
    QualityState,
)

SCHEMA_VERSION = "p4.s4.atomic.v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def stable_hash(payload: Any) -> str:
    blob = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def lineage_hash(lineage_ids: Iterable[str]) -> str:
    values = sorted({value for value in lineage_ids if value})
    return f"lineage-p4-s4-{stable_hash(values)[:24]}"


def build_atomic_panel(
    *,
    artifact_name: str,
    module_id: str,
    context: ExecutionContext,
    records: list[AtomicFeatureRecord],
    execution_status: ExecutionStatus = ExecutionStatus.PRODUCED,
    quality_status: QualityState = QualityState.PASS,
    quality_reasons: tuple[str, ...] = (),
    upstream_lineage_ids: Iterable[str] = (),
) -> AtomicFeaturePanel:
    ordered = sorted(records, key=lambda row: (row.decision_time, row.entity_id, row.feature_id, row.observer_id))
    record_payload = [row.model_dump(mode="json") for row in ordered]
    content_hash = stable_hash({"artifact_name": artifact_name, "records": record_payload})
    lineage = lineage_hash([*upstream_lineage_ids, *(row.record_lineage_id for row in ordered)])
    return AtomicFeaturePanel(
        artifact_id=f"{artifact_name}:{content_hash[:16]}",
        artifact_name=artifact_name,
        schema_version=SCHEMA_VERSION,
        pipeline_version=context.pipeline_version,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        as_of_time=context.as_of_time,
        created_at=context.created_at,
        content_hash=content_hash,
        lineage_id=lineage,
        execution_status=execution_status,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        records=tuple(ordered),
    )
