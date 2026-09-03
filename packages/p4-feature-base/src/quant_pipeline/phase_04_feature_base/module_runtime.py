from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .artifact_protocol import build_atomic_panel
from .economic_models import AtomicFeatureRecord, ExecutionStatus, QualityState
from .registry import specs_for_module
from .validation import parse_inputs

ComputeFunction = Callable[[tuple, tuple], list[AtomicFeatureRecord]]


def _record_quality(records: list[AtomicFeatureRecord]) -> tuple[ExecutionStatus, QualityState, tuple[str, ...]]:
    if not records:
        raise ValueError("records must not be empty")
    observed = sum(record.value is not None for record in records)
    degraded = any(record.quality_state is QualityState.DEGRADED for record in records)
    if observed == 0:
        return ExecutionStatus.DEGRADED, QualityState.DEGRADED, ("NO_OBSERVED_FEATURE_VALUES",)
    if degraded:
        return ExecutionStatus.PRODUCED, QualityState.DEGRADED, ("INPUT_QUALITY_DEGRADED",)
    return ExecutionStatus.PRODUCED, QualityState.PASS, ()


def execute_atomic_module(
    *,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any],
    module_id: str,
    artifact_name: str,
    supported_observers: set[str],
    compute: ComputeFunction,
    empty_data_status: ExecutionStatus = ExecutionStatus.DEGRADED,
) -> dict[str, Any]:
    panel, registry, context = parse_inputs(inputs, config)
    specs = specs_for_module(registry, module_id, supported_observers)
    if not specs:
        artifact = build_atomic_panel(
            artifact_name=artifact_name,
            module_id=module_id,
            context=context,
            records=[],
            execution_status=ExecutionStatus.SKIPPED_NOT_AUTHORIZED,
            quality_status=QualityState.DEGRADED,
            quality_reasons=("NO_APPROVED_OBSERVERS",),
            upstream_lineage_ids=(panel.lineage_id, registry.lineage_id),
        )
    else:
        records = compute(panel.records, specs)
        if records:
            status, quality, reasons = _record_quality(records)
        else:
            status = empty_data_status
            quality = QualityState.DEGRADED
            reasons = ("NO_COMPATIBLE_SOURCE_RECORDS",)
        artifact = build_atomic_panel(
            artifact_name=artifact_name,
            module_id=module_id,
            context=context,
            records=records,
            execution_status=status,
            quality_status=quality,
            quality_reasons=reasons,
            upstream_lineage_ids=(panel.lineage_id, registry.lineage_id),
        )
    return {
        "module_id": module_id,
        "execution_status": artifact.execution_status.value,
        "outputs": {artifact_name: artifact.model_dump(mode="json")},
    }
