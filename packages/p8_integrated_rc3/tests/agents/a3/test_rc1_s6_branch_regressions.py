from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.agent3_integration import (
    parse_lifecycle_context_json,
    parse_risk_bundle_json,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.api import run_s5
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.enums import DiscreteStatus
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.domain.hedge_problem import (
    HedgeProblemMetadata,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.artifacts import (
    EmergencyPlan,
    HedgeAdjustment,
    LifecycleLegDecision,
    LifecyclePlan,
    LiquidationStep,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.enums import (
    AuthorizationActionType,
    AuthorizationStatus,
    CandidateType,
    EmergencyStatus,
    HedgeStatus,
    InstrumentType,
    LifecycleAction,
    LifecycleStatus,
    OptionRight,
    OptionStyle,
    PositionSide,
    RiskGateStatus,
    SettlementType,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.models.inputs import (
    CandidateLifecycleInput,
    EmergencyState,
    LifecycleLegInput,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.modules import (
    emergency_planner,
    finalizer,
    hedge_planner,
    lifecycle_engine,
    risk_gate,
)
from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.ports.solvers import SolverResult

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 18, 0, 1, tzinfo=timezone.utc)


def _base():
    risk = parse_risk_bundle_json((ROOT / "fixtures/risk_bundle.json").read_bytes())
    context = parse_lifecycle_context_json((ROOT / "fixtures/s6_context.json").read_bytes())
    s5 = run_s5(risk, processing_time=NOW)
    policies = context.payload.policy_context
    gate = risk_gate.run_module(risk, s5, policies.risk_gate)
    return risk, context, s5, policies, gate


def _option_leg(**updates) -> LifecycleLegInput:
    values = dict(
        leg_id="LEG1",
        instrument_id="OPT1",
        instrument_type=InstrumentType.OPTION,
        side=PositionSide.LONG,
        quantity_per_candidate_unit=1.0,
        option_style=OptionStyle.AMERICAN,
        option_right=OptionRight.CALL,
        settlement_type=SettlementType.CASH,
        strike=100.0,
        underlying_price=110.0,
        mark_value_per_unit=9.0,
        intrinsic_value_per_unit=10.0,
        time_value_per_unit=0.1,
        dividend_present_value_per_unit=1.0,
        exercise_fee_per_unit=0.0,
        expiration_at=NOW + timedelta(days=1),
        exercise_cutoff_at=NOW + timedelta(hours=23),
        borrow_available=True,
        exercise_supported=True,
        assignment_supported=True,
        settlement_supported=True,
        close_supported=True,
        roll_supported=True,
        roll_target_instrument_id="OPT2",
    )
    values.update(updates)
    expiration = values["expiration_at"]
    cutoff = values.get("exercise_cutoff_at")
    if cutoff is not None and expiration is not None and cutoff > expiration:
        values["exercise_cutoff_at"] = None
    return LifecycleLegInput(**values)


def _lifecycle_plan(status=LifecycleStatus.SUPPORTED, decisions=(), reasons=()):
    return LifecyclePlan(
        status=status,
        decisions=decisions,
        unsupported_candidate_ids=("C1",) if status is LifecycleStatus.BLOCKED else (),
        plan_hash="1" * 64,
        reason_codes=reasons,
    )


def _emergency_plan(status=EmergencyStatus.NOT_TRIGGERED, steps=(), proven=True, reasons=()):
    return EmergencyPlan(
        status=status,
        steps=steps,
        total_margin_relief=sum(x.margin_relief for x in steps),
        total_capital_relief=sum(x.capital_relief for x in steps),
        total_maximum_loss_relief=sum(x.maximum_loss_relief for x in steps),
        estimated_total_cost=sum(x.estimated_transaction_cost for x in steps),
        feasibility_proven=proven,
        plan_hash="2" * 64,
        reason_codes=reasons,
    )


def test_lifecycle_option_decision_matrix_and_missing_context():
    _, context, _, policies, _ = _base()
    policy = policies.lifecycle

    cash_expired = _option_leg(expiration_at=NOW - timedelta(seconds=1))
    assert lifecycle_engine._option_action(cash_expired, NOW, policy)[0] is LifecycleAction.CASH_SETTLE

    exercise_expired = _option_leg(
        expiration_at=NOW - timedelta(seconds=1),
        settlement_type=SettlementType.NONE,
        settlement_supported=False,
    )
    assert lifecycle_engine._option_action(exercise_expired, NOW, policy)[0] is LifecycleAction.EXERCISE

    assign_expired = _option_leg(
        side=PositionSide.SHORT,
        expiration_at=NOW - timedelta(seconds=1),
        settlement_type=SettlementType.NONE,
        settlement_supported=False,
        exercise_supported=False,
    )
    assert lifecycle_engine._option_action(assign_expired, NOW, policy)[0] is LifecycleAction.ALLOW_ASSIGNMENT

    physical_expired = _option_leg(
        expiration_at=NOW - timedelta(seconds=1),
        settlement_type=SettlementType.PHYSICAL,
        exercise_supported=False,
        assignment_supported=False,
    )
    assert lifecycle_engine._option_action(physical_expired, NOW, policy)[0] is LifecycleAction.PHYSICAL_SETTLE

    unsupported_expired = _option_leg(
        expiration_at=NOW - timedelta(seconds=1),
        settlement_type=SettlementType.NONE,
        settlement_supported=False,
        exercise_supported=False,
        assignment_supported=False,
    )
    assert lifecycle_engine._option_action(unsupported_expired, NOW, policy)[0] is LifecycleAction.UNSUPPORTED

    assert lifecycle_engine._option_action(_option_leg(), NOW, policy)[0] is LifecycleAction.EXERCISE

    short_risk = _option_leg(
        side=PositionSide.SHORT,
        dividend_present_value_per_unit=0.0,
        time_value_per_unit=0.005,
    )
    assert lifecycle_engine._option_action(short_risk, NOW, policy)[0] is LifecycleAction.PREVENT_ASSIGNMENT

    close_window = _option_leg(
        expiration_at=NOW + timedelta(seconds=policy.close_before_expiry_seconds),
        dividend_present_value_per_unit=0.0,
        intrinsic_value_per_unit=0.0,
        mark_value_per_unit=1.0,
    )
    assert lifecycle_engine._option_action(close_window, NOW, policy)[0] is LifecycleAction.CLOSE

    roll_seconds = max(policy.close_before_expiry_seconds + 1, policy.roll_before_expiry_seconds)
    roll_window = _option_leg(
        expiration_at=NOW + timedelta(seconds=roll_seconds),
        close_supported=False,
        dividend_present_value_per_unit=0.0,
        intrinsic_value_per_unit=0.0,
        mark_value_per_unit=1.0,
    )
    assert lifecycle_engine._option_action(roll_window, NOW, policy)[0] is LifecycleAction.ROLL

    hold = _option_leg(
        expiration_at=NOW + timedelta(seconds=policy.roll_before_expiry_seconds + 10),
        dividend_present_value_per_unit=0.0,
        intrinsic_value_per_unit=0.0,
        mark_value_per_unit=1.0,
    )
    assert lifecycle_engine._option_action(hold, NOW, policy)[0] is LifecycleAction.HOLD

    linear = LifecycleLegInput(
        leg_id="LIN1",
        instrument_id="UND1",
        instrument_type=InstrumentType.UNDERLYING,
        side=PositionSide.LONG,
        quantity_per_candidate_unit=1.0,
        settlement_type=SettlementType.NONE,
        mark_value_per_unit=100.0,
        intrinsic_value_per_unit=0.0,
        time_value_per_unit=0.0,
    )
    decision = lifecycle_engine._decide_leg("C1", linear, 2.0, NOW, policy)
    assert decision.action is LifecycleAction.HOLD
    assert decision.quantity == 2.0

    risk, _, s5, _, _ = _base()
    missing = lifecycle_engine.run_module(risk, s5, (), policy, NOW)
    assert missing.status is LifecycleStatus.BLOCKED
    assert missing.unsupported_candidate_ids == ("C1",)

    no_action = s5.model_copy(
        update={
            "payload": s5.payload.model_copy(
                update={
                    "mpc_plan": s5.payload.mpc_plan.model_copy(
                        update={"first_actions": (), "future_plan": ()}
                    ),
                    "discrete_target": s5.payload.discrete_target.model_copy(
                        update={"status": DiscreteStatus.NO_ACTION_VALID, "quantities": ()}
                    ),
                }
            )
        }
    )
    assert lifecycle_engine.run_module(risk, no_action, context.payload.lifecycle_candidates, policy, NOW).status is LifecycleStatus.NO_ACTION_VALID


def test_lifecycle_run_module_blocks_unsupported_option():
    risk, _, s5, policies, _ = _base()
    option_candidate = CandidateLifecycleInput(
        candidate_id="C1",
        candidate_type=CandidateType.OPTION_STRUCTURE,
        legs=(
            _option_leg(
                expiration_at=NOW - timedelta(seconds=1),
                settlement_type=SettlementType.NONE,
                settlement_supported=False,
                exercise_supported=False,
                assignment_supported=False,
            ),
        ),
    )
    plan = lifecycle_engine.run_module(risk, s5, (option_candidate,), policies.lifecycle, NOW)
    assert plan.status is LifecycleStatus.BLOCKED
    assert plan.unsupported_candidate_ids == ("C1",)


def test_hedge_preconditions_adjustments_paths_and_acceptance(monkeypatch):
    risk, _, s5, policies, approved_gate = _base()
    hp = policies.hedge

    no_action_gate = approved_gate.model_copy(update={"status": RiskGateStatus.NO_ACTION_VALID})
    assert hedge_planner._precondition(no_action_gate, hp).status is HedgeStatus.NO_ACTION_VALID
    assert hedge_planner._precondition(approved_gate, hp.model_copy(update={"enabled": False})).status is HedgeStatus.DISABLED
    assert hedge_planner._precondition(approved_gate, hp).status is HedgeStatus.NOT_NEEDED

    blocked_gate = approved_gate.model_copy(update={"status": RiskGateStatus.RISK_BLOCKED})
    no_eligible = hedge_planner.run_module(risk, s5, blocked_gate, hp, policies.risk_gate)
    assert no_eligible.status is HedgeStatus.INFEASIBLE

    metadata = HedgeProblemMetadata(
        hedge_ids=("C1",),
        steps=(1.0,),
        base_losses=(1.0,),
        probabilities=(1.0,),
        variable_count=4,
    )
    adjustments, hedged = hedge_planner._adjustments(risk, {"C1": 0.0}, metadata, np.array([2.0]))
    assert adjustments[0].adjustment_quantity == 2.0
    assert hedged["C1"] == 2.0
    zero_adjustments, _ = hedge_planner._adjustments(risk, {"C1": 0.0}, metadata, np.array([0.0]))
    assert zero_adjustments == ()

    paths = hedge_planner._post_hedge_paths(s5, {"C1": 2.0, "UNKNOWN": 1.0})
    assert paths["C1"][0] == 2.0
    assert "UNKNOWN" not in paths

    base_metric = approved_gate.horizon_metrics[0].model_copy(update={"cvar": 10.0})
    post_metric = approved_gate.horizon_metrics[0].model_copy(update={"cvar": 5.0})
    base_gate = approved_gate.model_copy(update={"horizon_metrics": (base_metric,)})
    post_gate = approved_gate.model_copy(update={"horizon_metrics": (post_metric,)})
    adjustment = HedgeAdjustment(
        candidate_id="C1",
        current_target_quantity=5.0,
        adjustment_quantity=-1.0,
        hedged_target_quantity=4.0,
        estimated_transaction_cost=0.0,
    )
    accepted = hedge_planner._final_plan((adjustment,), base_gate, post_gate, hp)
    assert accepted.status is HedgeStatus.ACCEPTED
    rejected_cost = hedge_planner._final_plan(
        (adjustment.model_copy(update={"estimated_transaction_cost": hp.maximum_cost + 1.0}),),
        base_gate,
        post_gate,
        hp,
    )
    assert rejected_cost.status is HedgeStatus.REJECTED
    missing_cvar = hedge_planner._final_plan(
        (),
        base_gate.model_copy(update={"horizon_metrics": ()}),
        post_gate,
        hp,
    )
    assert missing_cvar.reason_codes == ("HEDGE_CVAR_UNAVAILABLE",)

    built = hedge_planner.build_hedge_problem(
        risk,
        {"C1": 5.0},
        hp.model_copy(update={"approved_hedge_candidate_ids": ("C1",)}),
    )
    assert built is not None
    monkeypatch.setattr(hedge_planner, "build_hedge_problem", lambda *args, **kwargs: built)
    monkeypatch.setattr(
        hedge_planner.ScipyHighsMilpAdapter,
        "solve",
        lambda self, problem: SolverResult(False, 2, "infeasible", None, None),
    )
    failed = hedge_planner.run_module(
        risk,
        s5,
        blocked_gate,
        hp.model_copy(update={"approved_hedge_candidate_ids": ("C1",)}),
        policies.risk_gate,
    )
    assert failed.reason_codes == ("HEDGE_SOLVER_INFEASIBLE",)


def test_emergency_planner_helper_and_failure_paths(monkeypatch):
    risk, _, s5, policies, _ = _base()
    ep = policies.emergency
    state = EmergencyState(required_margin_relief=1.0, trigger_reason_codes=("MARGIN",))

    assert emergency_planner._triggered(EmergencyState()) is False
    assert emergency_planner._triggered(state) is True
    disabled = emergency_planner.run_module(risk, s5, state, ep.model_copy(update={"enabled": False}))
    assert disabled.status is EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN

    monkeypatch.setattr(emergency_planner, "build_emergency_problem", lambda *args, **kwargs: None)
    no_problem = emergency_planner.run_module(risk, s5, state, ep)
    assert no_problem.reason_codes == ("NO_ELIGIBLE_LIQUIDATION_PROBLEM",)

    from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.domain.emergency_problem import EmergencyProblemMetadata
    from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.ports.solvers import LinearMixedIntegerProblem

    problem = LinearMixedIntegerProblem(
        objective=np.array([1.0]),
        lower_bounds=np.array([0.0]),
        upper_bounds=np.array([5.0]),
        integrality=np.array([1]),
        a_lower=np.array([1.0]),
        a_matrix=np.array([[1.0]]),
        a_upper=np.array([np.inf]),
        time_limit_seconds=1.0,
        mip_relative_gap=0.0,
    )
    metadata = EmergencyProblemMetadata(candidate_ids=("C1",), steps=(1.0,), directions=(-1.0,))
    monkeypatch.setattr(emergency_planner, "build_emergency_problem", lambda *args, **kwargs: (problem, metadata))
    monkeypatch.setattr(
        emergency_planner.ScipyHighsMilpAdapter,
        "solve",
        lambda self, problem: SolverResult(False, 2, "infeasible", None, None),
    )
    failed = emergency_planner.run_module(risk, s5, state, ep)
    assert failed.reason_codes == ("LIQUIDATION_SOLVER_INFEASIBLE",)

    steps = emergency_planner._build_steps(risk, {"C1": 5.0}, metadata, np.array([2.0]))
    assert steps[0].resulting_target_quantity == 3.0
    assert emergency_planner._totals(steps) == (2.0, 2.0, 2.0, 0.0)
    assert emergency_planner._relief_proven(emergency_planner._totals(steps), state)
    assert emergency_planner._final_plan(steps, emergency_planner._totals(steps), True).status is EmergencyStatus.PLAN_AVAILABLE
    assert emergency_planner._final_plan(steps, emergency_planner._totals(steps), False).status is EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN


def test_finalizer_status_matrix_and_lifecycle_only_authorization():
    _, _, s5, policies, gate = _base()
    hedge = hedge_planner._empty(HedgeStatus.NOT_NEEDED, "NOT_NEEDED")
    lifecycle = _lifecycle_plan()
    emergency = _emergency_plan()

    normal = finalizer.run_module(s5, gate, hedge, lifecycle, emergency, policies.authorization, NOW)
    assert normal.status is AuthorizationStatus.AUTHORIZED
    assert normal.authorized_actions[0].action_type is AuthorizationActionType.TARGET

    blocked_gate = gate.model_copy(update={"status": RiskGateStatus.RISK_BLOCKED, "reason_codes": ("LIMIT",)})
    blocked = finalizer.run_module(s5, blocked_gate, hedge, lifecycle, emergency, policies.authorization, NOW)
    assert blocked.status is AuthorizationStatus.RISK_BLOCKED

    blocked_lifecycle = finalizer.run_module(
        s5,
        gate,
        hedge,
        _lifecycle_plan(LifecycleStatus.BLOCKED, reasons=("LIFE",)),
        emergency,
        policies.authorization,
        NOW,
    )
    assert blocked_lifecycle.status is AuthorizationStatus.LIFECYCLE_BLOCKED

    unsafe = finalizer.run_module(
        s5,
        gate,
        hedge,
        lifecycle,
        _emergency_plan(EmergencyStatus.NO_SAFE_LIQUIDATION_PLAN, proven=False, reasons=("NO_SAFE",)),
        policies.authorization,
        NOW,
    )
    assert unsafe.status is AuthorizationStatus.RISK_BLOCKED

    step = LiquidationStep(
        sequence=1,
        candidate_id="C1",
        current_target_quantity=5.0,
        reduction_quantity=-2.0,
        resulting_target_quantity=3.0,
        margin_relief=2.0,
        capital_relief=2.0,
        maximum_loss_relief=2.0,
        estimated_transaction_cost=0.0,
    )
    emergency_auth = finalizer.run_module(
        s5,
        gate,
        hedge,
        lifecycle,
        _emergency_plan(EmergencyStatus.PLAN_AVAILABLE, (step,), True),
        policies.authorization,
        NOW,
    )
    assert emergency_auth.status is AuthorizationStatus.EMERGENCY_AUTHORIZED
    assert emergency_auth.authorized_actions[0].action_type is AuthorizationActionType.EMERGENCY

    expired = finalizer.run_module(
        s5,
        gate,
        hedge,
        lifecycle,
        emergency,
        policies.authorization,
        s5.payload.mpc_plan.valid_until,
    )
    assert expired.status is AuthorizationStatus.INFEASIBLE

    lifecycle_decision = LifecycleLegDecision(
        candidate_id="C1",
        leg_id="LEG1",
        instrument_id="OPT1",
        action=LifecycleAction.CLOSE,
        quantity=5.0,
        effective_at=NOW,
        reason_codes=("CLOSE_WINDOW",),
    )
    no_action_gate = gate.model_copy(update={"status": RiskGateStatus.NO_ACTION_VALID})
    lifecycle_only = finalizer.run_module(
        s5,
        no_action_gate,
        hedge,
        _lifecycle_plan(decisions=(lifecycle_decision,)),
        emergency,
        policies.authorization,
        NOW,
    )
    assert lifecycle_only.status is AuthorizationStatus.AUTHORIZED
    assert {a.action_type for a in lifecycle_only.authorized_actions} == {AuthorizationActionType.LIFECYCLE}


def test_independent_gate_blocks_missing_required_greek_and_finalizer_rejects_orphans():
    risk, _, s5, policies, gate = _base()
    from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import GreekLimit
    from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.domain.risk_evaluation import evaluate_target
    from quant_pipeline.phase_08_portfolio_control.s06_risk_lifecycle.domain.target import target_paths

    missing_limit = GreekLimit(
        greek_name="VEGA",
        minimum_by_horizon=(-100.0, -100.0),
        maximum_by_horizon=(100.0, 100.0),
    )
    risk_with_missing = risk.model_copy(
        update={
            "payload": risk.payload.model_copy(
                update={
                    "risk_limits": risk.payload.risk_limits.model_copy(
                        update={"greek_limits": (missing_limit,)}
                    )
                }
            )
        }
    )
    report = evaluate_target(
        risk_with_missing,
        target_paths(s5),
        policies.risk_gate,
        "3" * 64,
        True,
    )
    assert report.status is RiskGateStatus.RISK_BLOCKED
    assert "REQUIRED_GREEK_UNAVAILABLE" in report.reason_codes
    assert report.exposure_limits[0].available is False

    orphan_adjustment = HedgeAdjustment(
        candidate_id="ORPHAN",
        current_target_quantity=0.0,
        adjustment_quantity=1.0,
        hedged_target_quantity=1.0,
        estimated_transaction_cost=0.0,
    )
    orphan_hedge = hedge_planner._empty(HedgeStatus.ACCEPTED, "TEST").model_copy(
        update={"adjustments": (orphan_adjustment,)}
    )
    with pytest.raises(ValueError, match="absent from first-horizon target"):
        finalizer.run_module(
            s5,
            gate,
            orphan_hedge,
            _lifecycle_plan(),
            _emergency_plan(),
            policies.authorization,
            NOW,
        )

    orphan_lifecycle = _lifecycle_plan(
        decisions=(
            LifecycleLegDecision(
                candidate_id="ORPHAN",
                leg_id="LEG-X",
                instrument_id="OPT-X",
                action=LifecycleAction.CLOSE,
                quantity=1.0,
                effective_at=NOW,
            ),
        )
    )
    with pytest.raises(KeyError):
        finalizer.run_module(
            s5,
            gate,
            hedge_planner._empty(HedgeStatus.NOT_NEEDED, "TEST"),
            orphan_lifecycle,
            _emergency_plan(),
            policies.authorization,
            NOW,
        )
