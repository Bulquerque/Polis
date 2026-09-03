from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from .atomic_inputs import parse_atomic_panels
from .economic_errors import ContractError
from .economic_models import ExecutionStatus, QualityState
from .perspective_models import PerspectiveFeatureRecord, PerspectiveSpec
from .perspective_protocol import build_perspective_panel
from .perspective_validation import parse_registry_and_context

Compute = Callable[
    [tuple[Any, ...], tuple[PerspectiveSpec, ...]],
    list[PerspectiveFeatureRecord],
]


def _context_mismatches(panels: tuple[Any, ...], context: Any) -> list[str]:
    return [
        panel.artifact_name
        for panel in panels
        if (
            panel.run_id != context.run_id
            or panel.cycle_id != context.cycle_id
            or panel.as_of_time != context.as_of_time
            or panel.pipeline_version != context.pipeline_version
        )
    ]


def _artifact_without_records(
    *,
    artifact_name: str,
    module_id: str,
    context: Any,
    upstream: list[str],
    status: ExecutionStatus,
    reason: str,
):
    return build_perspective_panel(
        artifact_name=artifact_name,
        module_id=module_id,
        context=context,
        records=[],
        execution_status=status,
        quality_status=QualityState.DEGRADED,
        quality_reasons=(reason,),
        upstream_lineage_ids=upstream,
    )


def _quality_summary(
    output: list[PerspectiveFeatureRecord],
    specs: tuple[PerspectiveSpec, ...],
) -> tuple[ExecutionStatus, QualityState, tuple[str, ...]]:
    observed = sum(record.value is not None for record in output)
    produced = {record.hypothesis_id for record in output if record.value is not None}
    missing = sorted(spec.hypothesis_id for spec in specs if spec.hypothesis_id not in produced)
    degraded = any(record.quality_state is QualityState.DEGRADED for record in output)
    reasons: list[str] = []
    if degraded:
        reasons.append("INPUT_OR_OUTPUT_DEGRADED")
    if not observed:
        reasons.append("NO_OBSERVED_PERSPECTIVES")
    if missing:
        reasons.append("HYPOTHESES_WITHOUT_OBSERVED_VALUES:" + ",".join(missing))
    status = ExecutionStatus.PRODUCED if observed else ExecutionStatus.DEGRADED
    quality = QualityState.DEGRADED if degraded or missing or not observed else QualityState.PASS
    return status, quality, tuple(reasons)


def _authorized_specs(
    registry: Any,
    module_id: str,
    supported_observers: set[str],
) -> tuple[PerspectiveSpec, ...]:
    specs = tuple(
        record for record in registry.records if record.module_id == module_id and record.enabled
    )
    unknown = sorted(
        {record.observer_id for record in specs if record.observer_id not in supported_observers}
    )
    if unknown:
        raise ContractError(
            f"{module_id.replace('.', '_')}_UNKNOWN_OBSERVER",
            "unsupported perspective observers",
            details={"observer_ids": unknown},
        )
    return specs


def _atomic_inputs(
    inputs: Mapping[str, Any],
    required_panels: tuple[str, ...],
    context: Any,
    module_id: str,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    try:
        panels, records = parse_atomic_panels(inputs, required_panels)
    except ValidationError as exc:
        raise ContractError(
            f"{module_id.replace('.', '_')}_ATOMIC_SCHEMA_INVALID",
            "atomic input validation failed",
            details={"errors": exc.errors(include_url=False)},
        ) from exc
    mismatched = _context_mismatches(panels, context)
    if mismatched:
        raise ContractError(
            f"{module_id.replace('.', '_')}_ATOMIC_CONTEXT_MISMATCH",
            "atomic panels do not match execution context",
            details={"artifacts": sorted(mismatched)},
        )
    return panels, records


def _materialize_artifact(
    *,
    artifact_name: str,
    module_id: str,
    context: Any,
    upstream: list[str],
    specs: tuple[PerspectiveSpec, ...],
    records: tuple[Any, ...],
    compute: Compute,
):
    if not specs:
        return _artifact_without_records(
            artifact_name=artifact_name,
            module_id=module_id,
            context=context,
            upstream=upstream,
            status=ExecutionStatus.SKIPPED_NOT_AUTHORIZED,
            reason="NO_APPROVED_HYPOTHESES",
        )
    if not records:
        return _artifact_without_records(
            artifact_name=artifact_name,
            module_id=module_id,
            context=context,
            upstream=upstream,
            status=ExecutionStatus.UNAVAILABLE_UPSTREAM,
            reason="NO_REQUIRED_ATOMIC_RECORDS",
        )
    output = compute(records, specs)
    status, quality, reasons = _quality_summary(output, specs)
    return build_perspective_panel(
        artifact_name=artifact_name,
        module_id=module_id,
        context=context,
        records=output,
        execution_status=status,
        quality_status=quality,
        quality_reasons=reasons,
        upstream_lineage_ids=upstream,
    )


def execute_perspective_module(
    *,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any],
    module_id: str,
    artifact_name: str,
    required_panels: tuple[str, ...],
    supported_observers: set[str],
    compute: Compute,
) -> dict[str, Any]:
    registry, context = parse_registry_and_context(inputs, config)
    specs = _authorized_specs(registry, module_id, supported_observers)
    panels, records = _atomic_inputs(inputs, required_panels, context, module_id)
    upstream = [registry.lineage_id, *(panel.lineage_id for panel in panels)]
    artifact = _materialize_artifact(
        artifact_name=artifact_name,
        module_id=module_id,
        context=context,
        upstream=upstream,
        specs=specs,
        records=records,
        compute=compute,
    )
    return {
        "module_id": module_id,
        "execution_status": artifact.execution_status.value,
        "outputs": {artifact_name: artifact.model_dump(mode="json")},
    }
