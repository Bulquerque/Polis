from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle

from ..adapters.scipy_highs import ScipyHighsMilpAdapter
from ..domain.hedge_problem import HedgeProblemMetadata, build_hedge_problem
from ..domain.risk_evaluation import evaluate_target
from ..domain.target import first_horizon_target_portfolio, target_paths
from ..models.artifacts import HedgeAdjustment, HedgePlan, IndependentRiskGateReport
from ..models.enums import HedgeStatus, RiskGateStatus
from ..models.policies import HedgePolicy, RiskGatePolicy


def _empty(status: HedgeStatus, reason: str) -> HedgePlan:
    draft = HedgePlan(
        status=status,
        adjustments=(),
        base_cvar=None,
        post_hedge_cvar=None,
        cvar_reduction=0,
        estimated_cost=0,
        post_hedge_risk_gate=None,
        plan_hash="0" * 64,
        reason_codes=(reason,),
    )
    unsigned = draft.model_copy(update={"plan_hash": "0" * 64})
    return draft.model_copy(update={"plan_hash": canonical_sha256(unsigned)})


def _precondition(gate: IndependentRiskGateReport, policy: HedgePolicy) -> HedgePlan | None:
    if gate.status == RiskGateStatus.NO_ACTION_VALID:
        return _empty(HedgeStatus.NO_ACTION_VALID, "NO_ACTION_VALID")
    if not policy.enabled:
        return _empty(HedgeStatus.DISABLED, "HEDGE_DISABLED")
    if gate.status == RiskGateStatus.APPROVED:
        return _empty(HedgeStatus.NOT_NEEDED, "RISK_GATE_APPROVED")
    return None


def _adjustments(
    risk_bundle: DecisionReadyRiskBundle,
    target: dict[str, float],
    metadata: HedgeProblemMetadata,
    solution,
) -> tuple[tuple[HedgeAdjustment, ...], dict[str, float]]:
    candidate_map = {candidate.candidate_id: candidate for candidate in risk_bundle.payload.candidates}
    hedged_target = dict(target)
    adjustments = []
    for index, (candidate_id, step) in enumerate(
        zip(metadata.hedge_ids, metadata.steps, strict=True)
    ):
        candidate = candidate_map[candidate_id]
        adjustment = round(solution[index]) * step
        current = target.get(candidate_id, candidate.current_quantity)
        hedged_target[candidate_id] = current + adjustment
        if abs(adjustment) <= 1e-10:
            continue
        adjustments.append(
            HedgeAdjustment(
                candidate_id=candidate_id,
                current_target_quantity=current,
                adjustment_quantity=adjustment,
                hedged_target_quantity=hedged_target[candidate_id],
                estimated_transaction_cost=abs(adjustment)
                * candidate.transaction_cost_per_unit,
            )
        )
    return tuple(adjustments), hedged_target


def _post_hedge_paths(
    s5_bundle: S5ResultBundle,
    hedged_target: dict[str, float],
) -> dict[str, tuple[float, ...]]:
    paths = target_paths(s5_bundle)
    for candidate_id, value in hedged_target.items():
        if candidate_id in paths:
            paths[candidate_id] = (value,) + paths[candidate_id][1:]
    return paths


def _accepted(
    post_gate: IndependentRiskGateReport,
    reduction: float,
    cost: float,
    policy: HedgePolicy,
) -> bool:
    return (
        post_gate.status == RiskGateStatus.APPROVED
        and reduction + 1e-12 >= policy.minimum_cvar_reduction
        and cost <= policy.maximum_cost + 1e-12
    )


def _final_plan(
    adjustments: tuple[HedgeAdjustment, ...],
    gate: IndependentRiskGateReport,
    post_gate: IndependentRiskGateReport,
    policy: HedgePolicy,
) -> HedgePlan:
    base_cvar = gate.horizon_metrics[0].cvar if gate.horizon_metrics else None
    post_cvar = post_gate.horizon_metrics[0].cvar if post_gate.horizon_metrics else None
    cost = sum(adjustment.estimated_transaction_cost for adjustment in adjustments)
    if base_cvar is None or post_cvar is None:
        draft = HedgePlan(
            status=HedgeStatus.REJECTED,
            adjustments=adjustments,
            base_cvar=base_cvar,
            post_hedge_cvar=post_cvar,
            cvar_reduction=0,
            estimated_cost=cost,
            post_hedge_risk_gate=post_gate,
            plan_hash="0" * 64,
            reason_codes=("HEDGE_CVAR_UNAVAILABLE",),
        )
        unsigned = draft.model_copy(update={"plan_hash": "0" * 64})
        return draft.model_copy(update={"plan_hash": canonical_sha256(unsigned)})
    reduction = max(0.0, base_cvar - post_cvar)
    accepted = _accepted(post_gate, reduction, cost, policy)
    draft = HedgePlan(
        status=HedgeStatus.ACCEPTED if accepted else HedgeStatus.REJECTED,
        adjustments=adjustments,
        base_cvar=base_cvar,
        post_hedge_cvar=post_cvar,
        cvar_reduction=reduction,
        estimated_cost=cost,
        post_hedge_risk_gate=post_gate,
        plan_hash="0" * 64,
        reason_codes=() if accepted else ("HEDGE_ACCEPTANCE_CRITERIA_NOT_MET",),
    )
    unsigned = draft.model_copy(update={"plan_hash": "0" * 64})
    return draft.model_copy(update={"plan_hash": canonical_sha256(unsigned)})


def run_module(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    gate: IndependentRiskGateReport,
    hedge_policy: HedgePolicy,
    gate_policy: RiskGatePolicy,
) -> HedgePlan:
    precondition = _precondition(gate, hedge_policy)
    if precondition is not None:
        return precondition
    target = first_horizon_target_portfolio(s5_bundle)
    built = build_hedge_problem(risk_bundle, target, hedge_policy)
    if built is None:
        return _empty(HedgeStatus.INFEASIBLE, "NO_ELIGIBLE_HEDGE_PROBLEM")
    problem, metadata = built
    result = ScipyHighsMilpAdapter().solve(problem)
    if not result.success or result.x is None:
        return _empty(HedgeStatus.INFEASIBLE, "HEDGE_SOLVER_INFEASIBLE")
    adjustments, hedged_target = _adjustments(risk_bundle, target, metadata, result.x)
    paths = _post_hedge_paths(s5_bundle, hedged_target)
    post_gate = evaluate_target(
        risk_bundle,
        paths,
        gate_policy,
        canonical_sha256(hedged_target),
        True,
    )
    return _final_plan(adjustments, gate, post_gate, hedge_policy)
