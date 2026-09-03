"""P6.S8 module implementations."""

from __future__ import annotations

from typing import Any

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.results import ModuleResult
from .services import (
    apply_cost_gate,
    apply_data_quality_gate,
    apply_liquidity_gate,
    apply_margin_gate,
    apply_maximum_loss_gate,
    final_sanity_and_risk,
    initial_structural_gate,
)


def _artifact(
    records: tuple[Any, ...],
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
        records=records,
        status=status,
    )


def structural(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S8.M01"
    records = initial_structural_gate(
        inputs["raw_strategy_candidate_panel"].records,
        configuration,
    )
    artifact = _artifact(records, "structural_gate_report", module_id, context)
    return ModuleResult(
        module_id=module_id,
        outputs={"structural_gate_report": artifact},
    )


def maxloss(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S8.M02"
    records = apply_maximum_loss_gate(
        inputs["structural_gate_report"].records,
        inputs["strategy_payoff_panel"].records,
        configuration,
    )
    artifact = _artifact(
        records,
        "maximum_loss_gate_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"maximum_loss_gate_report": artifact},
    )


def margin(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S8.M03"
    records = apply_margin_gate(
        inputs["maximum_loss_gate_report"].records,
        inputs["strategy_payoff_panel"].records,
        configuration,
    )
    artifact = _artifact(
        records,
        "margin_feasibility_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"margin_feasibility_report": artifact},
    )


def liquidity(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S8.M04"
    records = apply_liquidity_gate(
        inputs["margin_feasibility_report"].records,
        inputs["strategy_cost_liquidity_panel"].records,
        configuration,
    )
    artifact = _artifact(
        records,
        "liquidity_gate_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"liquidity_gate_report": artifact},
    )


def cost(inputs, configuration, context) -> ModuleResult:
    module_id = "P6.S8.M05"
    records = apply_cost_gate(
        inputs["liquidity_gate_report"].records,
        inputs["strategy_cost_liquidity_panel"].records,
        configuration,
    )
    artifact = _artifact(records, "cost_gate_report", module_id, context)
    return ModuleResult(
        module_id=module_id,
        outputs={"cost_gate_report": artifact},
    )


def quality(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S8.M06"
    records = apply_data_quality_gate(
        inputs["cost_gate_report"].records,
        inputs["strategy_greek_panel"].records,
    )
    artifact = _artifact(
        records,
        "data_quality_gate_report",
        module_id,
        context,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"data_quality_gate_report": artifact},
    )


def sanity(inputs, configuration, context) -> ModuleResult:
    del configuration
    module_id = "P6.S8.M07"
    qualifications, risks, rejections = final_sanity_and_risk(
        inputs["data_quality_gate_report"].records,
        inputs["raw_strategy_candidate_panel"].records,
        inputs["strategy_payoff_panel"].records,
        inputs["strategy_scenario_evaluation_panel"].records,
    )
    qualification_artifact = _artifact(
        qualifications,
        "strategy_qualification_panel",
        module_id,
        context,
    )
    risk_status = ArtifactStatus.COMPLETE if risks else ArtifactStatus.BLOCKED
    risk_artifact = _artifact(
        risks,
        "strategy_risk_panel",
        module_id,
        context,
        status=risk_status,
    )
    rejection_status = (
        ArtifactStatus.COMPLETE if rejections else ArtifactStatus.EMPTY_VALID
    )
    rejection_artifact = _artifact(
        rejections,
        "feasibility_rejection_report",
        module_id,
        context,
        status=rejection_status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={
            "strategy_qualification_panel": qualification_artifact,
            "strategy_risk_panel": risk_artifact,
            "feasibility_rejection_report": rejection_artifact,
        },
    )
