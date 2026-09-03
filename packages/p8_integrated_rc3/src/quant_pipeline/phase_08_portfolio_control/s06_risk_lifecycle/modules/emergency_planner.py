from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle

from ..adapters.scipy_highs import ScipyHighsMilpAdapter
from ..domain.emergency_problem import EmergencyProblemMetadata, build_emergency_problem
from ..domain.target import first_horizon_target_portfolio
from ..models.artifacts import EmergencyPlan, LiquidationStep
from ..models.enums import EmergencyStatus
from ..models.inputs import EmergencyState
from ..models.policies import EmergencyPolicy


def _empty(status: EmergencyStatus, reason: str, proven: bool) -> EmergencyPlan:
    draft = EmergencyPlan(
        status=status,
        steps=(),
        total_margin_relief=0,
        total_capital_relief=0,
        total_maximum_loss_relief=0,
        estimated_total_cost=0,
        feasibility_proven=proven,
        plan_hash="0" * 64,
        reason_codes=(reason,),
    )
    unsigned = draft.model_copy(update={"plan_hash": "0" * 64})
    return draft.model_copy(update={"plan_hash": canonical_sha256(unsigned)})


def _triggered(state: EmergencyState) -> bool:
    return any(
        (
            state.forced_liquidation_required,
            state.required_margin_relief > 0,
            state.required_capital_relief > 0,
            state.required_maximum_loss_relief > 0,
        )
    )


def _build_steps(
    risk_bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
    metadata: EmergencyProblemMetadata,
    solution,
) -> tuple[LiquidationStep, ...]:
    candidate_map = {candidate.candidate_id: candidate for candidate in risk_bundle.payload.candidates}
    raw_steps = []
    for candidate_id, step, direction, count in zip(
        metadata.candidate_ids,
        metadata.steps,
        metadata.directions,
        solution,
        strict=True,
    ):
        integer_count = round(count)
        if integer_count <= 0:
            continue
        reduction = direction * step * integer_count
        candidate = candidate_map[candidate_id]
        raw_steps.append(
            {
                "candidate_id": candidate_id,
                "current_target_quantity": target[candidate_id],
                "reduction_quantity": reduction,
                "resulting_target_quantity": target[candidate_id] + reduction,
                "margin_relief": abs(reduction) * candidate.margin_per_unit,
                "capital_relief": abs(reduction) * candidate.capital_per_unit,
                "maximum_loss_relief": abs(reduction) * candidate.maximum_loss_per_unit,
                "estimated_transaction_cost": abs(reduction)
                * candidate.transaction_cost_per_unit,
            }
        )
    raw_steps.sort(key=_priority_key)
    return tuple(
        LiquidationStep(sequence=index + 1, **values)
        for index, values in enumerate(raw_steps)
    )


def _priority_key(values: dict[str, float | str]) -> tuple[float, str]:
    total_relief = (
        float(values["margin_relief"])
        + float(values["capital_relief"])
        + float(values["maximum_loss_relief"])
    )
    score = -total_relief / (float(values["estimated_transaction_cost"]) + 1e-9)
    return score, str(values["candidate_id"])


def _totals(steps: tuple[LiquidationStep, ...]) -> tuple[float, float, float, float]:
    return (
        sum(step.margin_relief for step in steps),
        sum(step.capital_relief for step in steps),
        sum(step.maximum_loss_relief for step in steps),
        sum(step.estimated_transaction_cost for step in steps),
    )


def _relief_proven(totals: tuple[float, float, float, float], state: EmergencyState) -> bool:
    return (
        totals[0] + 1e-9 >= state.required_margin_relief
        and totals[1] + 1e-9 >= state.required_capital_relief
        and totals[2] + 1e-9 >= state.required_maximum_loss_relief
    )


def _final_plan(
    steps: tuple[LiquidationStep, ...],
    totals: tuple[float, float, float, float],
    proven: bool,
) -> EmergencyPlan:
    status = EmergencyStatus.PLAN_AVAILABLE if proven else EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN
    reasons = () if proven else ("RELIEF_TARGET_NOT_MET",)
    draft = EmergencyPlan(
        status=status,
        steps=steps,
        total_margin_relief=totals[0],
        total_capital_relief=totals[1],
        total_maximum_loss_relief=totals[2],
        estimated_total_cost=totals[3],
        feasibility_proven=proven,
        plan_hash="0" * 64,
        reason_codes=reasons,
    )
    unsigned = draft.model_copy(update={"plan_hash": "0" * 64})
    return draft.model_copy(update={"plan_hash": canonical_sha256(unsigned)})


def run_module(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    state: EmergencyState,
    policy: EmergencyPolicy,
) -> EmergencyPlan:
    if not _triggered(state):
        return _empty(EmergencyStatus.NOT_TRIGGERED, "EMERGENCY_NOT_TRIGGERED", True)
    if not policy.enabled:
        return _empty(
            EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN, "EMERGENCY_POLICY_DISABLED", False
        )
    target = first_horizon_target_portfolio(s5_bundle)
    built = build_emergency_problem(risk_bundle, target, state, policy)
    if built is None:
        return _empty(
            EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN,
            "NO_ELIGIBLE_LIQUIDATION_PROBLEM",
            False,
        )
    problem, metadata = built
    result = ScipyHighsMilpAdapter().solve(problem)
    if not result.success or result.x is None:
        return _empty(
            EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN,
            "LIQUIDATION_SOLVER_INFEASIBLE",
            False,
        )
    steps = _build_steps(risk_bundle, target, metadata, result.x)
    totals = _totals(steps)
    return _final_plan(steps, totals, _relief_proven(totals, state))
