"""P6.S4 module implementations."""

from __future__ import annotations

from typing import Any, Iterable

from ..domain.enums import CapabilityStatus
from ..domain.models import CapabilityRecord
from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .services import (
    complexity_gate,
    mutate_candidates,
    operator_registry,
    validate_mutation_traces,
)


def _artifact(
    records: Iterable[object],
    name: str,
    module_id: str,
    context: PhaseContext,
    *,
    status: ArtifactStatus | None = None,
):
    return build_artifact(
        artifact_type=name,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=tuple(records),
        status=status,
    )


def registry(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration,
) -> ModuleResult:
    del inputs
    module_id = "P6.S4.M01"
    records = operator_registry(configuration)
    artifact = _artifact(
        records,
        "mutation_operator_registry",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"mutation_operator_registry": artifact},
    )


def mutate(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration,
) -> ModuleResult:
    module_id = "P6.S4.M02"
    if not configuration.operational_mode.mutation_enabled:
        return _disabled_mutation_result(module_id, context)
    candidates, traces, applications = mutate_candidates(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["eligible_option_contract_panel"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        configuration,
    )
    outputs = {
        "mutated_strategy_candidate_panel_raw": _artifact(
            candidates,
            "mutated_strategy_candidate_panel_raw",
            module_id,
            context,
        ),
        "mutation_generation_trace_panel": _artifact(
            traces,
            "mutation_generation_trace_panel",
            module_id,
            context,
        ),
        "mutation_application_panel_raw": _artifact(
            applications,
            "mutation_application_panel_raw",
            module_id,
            context,
        ),
    }
    return ModuleResult(module_id=module_id, outputs=outputs)


def validate_trace(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration,
) -> ModuleResult:
    del configuration
    module_id = "P6.S4.M03"
    records = validate_mutation_traces(
        tuple(inputs["mutated_strategy_candidate_panel_raw"].records),
        tuple(inputs["mutation_application_panel_raw"].records),
    )
    artifact = _artifact(
        records,
        "mutation_application_panel",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"mutation_application_panel": artifact},
    )


def gate(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration,
) -> ModuleResult:
    module_id = "P6.S4.M04"
    candidates, rejections = complexity_gate(
        tuple(inputs["mutated_strategy_candidate_panel_raw"].records),
        tuple(inputs["mutation_application_panel"].records),
        configuration,
    )
    outputs = {
        "mutated_strategy_candidate_panel": _artifact(
            candidates,
            "mutated_strategy_candidate_panel",
            module_id,
            context,
        ),
        "mutation_rejection_report": _artifact(
            rejections,
            "mutation_rejection_report",
            module_id,
            context,
        ),
    }
    return ModuleResult(module_id=module_id, outputs=outputs)


def _disabled_mutation_result(
    module_id: str,
    context: PhaseContext,
) -> ModuleResult:
    capability = CapabilityRecord(
        capability="MUTATION",
        status=CapabilityStatus.UNAVAILABLE,
        reason_code="P6_CAPABILITY_DISABLED_BY_MODE",
        planned_wave=2,
    )
    empty = ArtifactStatus.EMPTY_VALID
    outputs = {
        "mutation_capability": _artifact(
            (capability,),
            "mutation_capability",
            module_id,
            context,
            status=ArtifactStatus.DEGRADED,
        ),
        "mutated_strategy_candidate_panel_raw": _artifact(
            (),
            "mutated_strategy_candidate_panel_raw",
            module_id,
            context,
            status=empty,
        ),
        "mutation_generation_trace_panel": _artifact(
            (),
            "mutation_generation_trace_panel",
            module_id,
            context,
            status=empty,
        ),
        "mutation_application_panel_raw": _artifact(
            (),
            "mutation_application_panel_raw",
            module_id,
            context,
            status=empty,
        ),
    }
    return ModuleResult(module_id=module_id, outputs=outputs)
