"""P6.S3 deterministic template-generation runner."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..foundation.artifacts import ArtifactEnvelope, ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult, SubphaseResult
from .modules.P6_S3_M01_single_instrument_generator import run as run_single
from .modules.P6_S3_M02_vertical_generator import run as run_vertical
from .modules.P6_S3_M03_volatility_structure_generator import run as run_volatility
from .modules.P6_S3_M04_skew_asymmetric_generator import run as run_skew
from .modules.P6_S3_M05_term_structure_generator import run as run_term
from .modules.P6_S3_M06_underlying_overlay_generator import run as run_overlay
from .modules.P6_S3_M07_template_parameter_planner import run as run_plan

_FAMILY_RUNNERS = (
    run_single,
    run_vertical,
    run_volatility,
    run_skew,
    run_term,
    run_overlay,
)


def _combined_artifact(
    *,
    records: Iterable[Any],
    artifact_type: str,
    context: PhaseContext,
    input_ids: Iterable[str],
) -> ArtifactEnvelope[Any]:
    record_tuple = tuple(records)
    return build_artifact(
        artifact_type=artifact_type,
        producer_module_id="P6.S3",
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=record_tuple,
        input_artifact_ids=input_ids,
        status=(
            ArtifactStatus.COMPLETE
            if record_tuple
            else ArtifactStatus.EMPTY_VALID
        ),
    )


def _collect_family_artifacts(
    state: dict[str, Any],
    suffix: str,
) -> tuple[str, ...]:
    return tuple(sorted(key for key in state if key.endswith(suffix)))


def _aggregate_outputs(
    state: dict[str, Any],
    context: PhaseContext,
) -> dict[str, Any]:
    candidate_keys = _collect_family_artifacts(state, "_candidates")
    trace_keys = _collect_family_artifacts(state, "_trace")
    rejection_keys = _collect_family_artifacts(state, "_rejections")
    candidates = tuple(
        record
        for key in candidate_keys
        for record in state[key].records
    )
    traces = tuple(
        record
        for key in trace_keys
        for record in state[key].records
    )
    rejections = tuple(
        record
        for key in rejection_keys
        for record in state[key].records
    )
    input_ids = tuple(state[key].artifact_id for key in candidate_keys)
    return {
        "raw_strategy_candidate_panel": _combined_artifact(
            records=candidates,
            artifact_type="raw_strategy_candidate_panel",
            context=context,
            input_ids=input_ids,
        ),
        "strategy_generation_trace_panel": _combined_artifact(
            records=traces,
            artifact_type="strategy_generation_trace_panel",
            context=context,
            input_ids=input_ids,
        ),
        "template_generation_rejection_report": _combined_artifact(
            records=rejections,
            artifact_type="template_generation_rejection_report",
            context=context,
            input_ids=input_ids,
        ),
    }


def run_subphase(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration: Any,
) -> SubphaseResult:
    """Run deterministic template planning and all Wave 1 families."""
    state = dict(inputs)
    results: list[ModuleResult] = []

    plan_result = run_plan(state, context, configuration)
    state.update(plan_result.outputs)
    results.append(plan_result)
    for runner in _FAMILY_RUNNERS:
        result = runner(state, context, configuration)
        state.update(result.outputs)
        results.append(result)

    outputs = {
        key: value
        for result in results
        for key, value in result.outputs.items()
        if key != "_template_plan"
    }
    outputs.update(_aggregate_outputs(state, context))
    outputs["_template_plan"] = state["_template_plan"]
    return SubphaseResult(
        subphase_id="P6.S3",
        module_results=tuple(results),
        outputs=outputs,
    )
