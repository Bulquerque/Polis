from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import ExecutionContext
from .modules.P4_S1_M01_phase2_handoff_validator import execute as execute_s1_m01
from .modules.P4_S1_M02_phase3_handoff_validator import execute as execute_s1_m02
from .modules.P4_S1_M03_boundary_consistency_gate import execute as execute_s1_m03
from .modules.P4_S1_M04_n_plus_1_variable_evolution_intake import execute as execute_s1_m04
from .modules.P4_S2_M01_temporal_semantics_resolver import execute as execute_s2_m01
from .modules.P4_S2_M02_entity_calendar_corporate_action_aligner import (
    execute as execute_s2_m02,
)
from .modules.P4_S2_M03_revision_freshness_missingness_mapper import (
    execute as execute_s2_m03,
)
from .modules.P4_S2_M04_canonical_observation_store_builder import execute as execute_s2_m04
from .modules.P4_S3_M01_phenomenon_perspective_registry import execute as execute_s3_m01
from .modules.P4_S3_M02_observer_spec_validator import execute as execute_s3_m02
from .modules.P4_S3_M03_causal_operator_engine import execute as execute_s3_m03
from .modules.P4_S3_M04_relational_stateful_operator_engine import execute as execute_s3_m04
from .modules.P4_S3_M05_hypothesis_passport_budget_gate import execute as execute_s3_m05
from .runtime.datetime_utils import utc_z


def _subphase_result(
    *,
    subphase_id: str,
    context: ExecutionContext,
    module_results: Mapping[str, Mapping[str, Any]],
    execution_order: list[str] | None = None,
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for result in module_results.values():
        outputs.update(result)
    response: dict[str, Any] = {
        "phase_id": "P4",
        "subphase_id": subphase_id,
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "module_results": dict(module_results),
        "outputs": outputs,
    }
    if execution_order is not None:
        response["execution_order"] = execution_order
    return response


def run_s1_subphase(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """Validate P2/P3 boundaries and register optional N+1 proposals."""
    m01 = execute_s1_m01(inputs, context)
    m02 = execute_s1_m02(inputs, context)
    m03 = execute_s1_m03(
        {
            "validated_phase2_bundle": m01["validated_phase2_bundle"],
            "validated_phase3_bundle": m02["validated_phase3_bundle"],
        },
        context,
        inputs,
    )
    m04_inputs: dict[str, Any] = {
        "validated_p4_boundary_bundle": m03["validated_p4_boundary_bundle"]
    }
    if "variable_evolution_input_manifest" in inputs:
        m04_inputs["variable_evolution_input_manifest"] = inputs[
            "variable_evolution_input_manifest"
        ]
    m04 = execute_s1_m04(m04_inputs, context)
    return _subphase_result(
        subphase_id="P4.S1",
        context=context,
        module_results={
            "P4.S1.M01": m01,
            "P4.S1.M02": m02,
            "P4.S1.M03": m03,
            "P4.S1.M04": m04,
        },
    )


def run_s2_subphase(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """Resolve temporal semantics and build the typed canonical observation store."""
    m01 = execute_s2_m01(inputs, context)
    m02 = execute_s2_m02(
        {"temporally_resolved_observation_bundle": m01["temporally_resolved_observation_bundle"]},
        context,
    )
    m03 = execute_s2_m03(
        {
            "entity_aligned_observation_bundle": m02["entity_aligned_observation_bundle"],
            "phase2_capability_matrix": inputs["phase2_capability_matrix"],
            "phase3_capability_matrix": inputs["phase3_capability_matrix"],
        },
        context,
    )
    m04 = execute_s2_m04(
        {"quality_enriched_observation_bundle": m03["quality_enriched_observation_bundle"]},
        context,
    )
    return _subphase_result(
        subphase_id="P4.S2",
        context=context,
        module_results={
            "P4.S2.M01": m01,
            "P4.S2.M02": m02,
            "P4.S2.M03": m03,
            "P4.S2.M04": m04,
        },
    )


def run_foundation(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """Run S1 and S2 as a deterministic vertical foundation slice."""
    s1 = run_s1_subphase(inputs, context)
    s2 = run_s2_subphase({**dict(inputs), **s1["outputs"]}, context)
    return {
        "phase_id": "P4",
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "subphases": {"P4.S1": s1, "P4.S2": s2},
        "outputs": {**s1["outputs"], **s2["outputs"]},
    }


def run_s3_subphase(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """Execute theory-first governance in topological order M01→M02→M05→M03/M04."""
    m01 = execute_s3_m01(
        {"observer_change_proposal_registry": inputs["observer_change_proposal_registry"]},
        context,
    )
    m02 = execute_s3_m02(m01, context)
    m05 = execute_s3_m05({**m01, **m02}, context)
    execution_inputs = {
        "canonical_observation_panel": inputs["canonical_observation_panel"],
        "approved_observer_execution_registry": m05["approved_observer_execution_registry"],
    }
    m03 = execute_s3_m03(execution_inputs, context)
    m04 = execute_s3_m04(execution_inputs, context)
    order = ["P4.S3.M01", "P4.S3.M02", "P4.S3.M05", "P4.S3.M03", "P4.S3.M04"]
    return _subphase_result(
        subphase_id="P4.S3",
        context=context,
        execution_order=order,
        module_results={
            "P4.S3.M01": m01,
            "P4.S3.M02": m02,
            "P4.S3.M05": m05,
            "P4.S3.M03": m03,
            "P4.S3.M04": m04,
        },
    )


def run_foundation_and_governance(
    inputs: Mapping[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    """Run the complete S1–S3 foundation and governance layer."""
    foundation = run_foundation(inputs, context)
    s3 = run_s3_subphase(foundation["outputs"], context)
    return {
        "phase_id": "P4",
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "subphases": {**foundation["subphases"], "P4.S3": s3},
        "outputs": {**foundation["outputs"], **s3["outputs"]},
    }


def run_subphase(inputs: Mapping[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """Backward-compatible alias for the qualified S1 runner."""
    return run_s1_subphase(inputs, context)


def run_phase(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility entry point with an explicit target-subphase selector."""
    phase_config = dict(config or {})
    context = ExecutionContext.from_mapping(phase_config.get("execution_context", phase_config))
    target = str(phase_config.get("target_subphase", "P4.S1")).upper()
    if target in {"P4.S1", "S1"}:
        return run_s1_subphase(inputs, context)
    if target in {"P4.S2", "S2"}:
        return run_s2_subphase(inputs, context)
    if target in {"FOUNDATION", "P4.S1-S2", "S1-S2"}:
        return run_foundation(inputs, context)
    if target in {"P4.S3", "S3"}:
        return run_s3_subphase(inputs, context)
    if target in {"P4.S1-S3", "S1-S3", "FOUNDATION_AND_GOVERNANCE"}:
        return run_foundation_and_governance(inputs, context)
    raise ValueError(f"unsupported target_subphase: {target!r}")
