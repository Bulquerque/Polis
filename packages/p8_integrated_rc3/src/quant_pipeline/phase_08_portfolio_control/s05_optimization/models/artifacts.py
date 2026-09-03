from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import Identifier, Sha256, TimeAwareModel
from .enums import ComparisonState, DiscreteStatus, RebalanceAction, SolverStatus
from .inputs import ArtifactEnvelope


class ObjectiveComponent(TimeAwareModel):
    component_id: Identifier
    component_type: Identifier
    weight: float
    unit: Identifier
    direction: Identifier


class CompiledPortfolioObjective(TimeAwareModel):
    candidate_ids: tuple[Identifier, ...]
    horizon_ids: tuple[Identifier, ...]
    expected_pnl_by_horizon_candidate: tuple[tuple[float, ...], ...]
    transaction_cost_by_candidate: tuple[float, ...]
    funding_cost_by_horizon_candidate: tuple[tuple[float, ...], ...]
    components: tuple[ObjectiveComponent, ...]
    ordinal_penalty_count: int = Field(ge=0)
    objective_hash: Sha256


class ConstraintConflict(TimeAwareModel):
    conflict_id: Identifier
    reason_code: Identifier
    candidate_id: Identifier | None = None
    detail: str


class CompiledConstraintSet(TimeAwareModel):
    candidate_ids: tuple[Identifier, ...]
    horizon_ids: tuple[Identifier, ...]
    candidate_bounds: tuple[tuple[float, float], ...]
    quantity_increments: tuple[float, ...]
    capital_limits: tuple[float, ...]
    margin_limits: tuple[float, ...]
    maximum_loss_limits: tuple[float, ...]
    liquidity_caps: tuple[tuple[float, ...], ...]
    maximum_turnover: float
    maximum_cvar: float | None
    constraint_count: int = Field(ge=0)
    conflicts: tuple[ConstraintConflict, ...] = ()
    constraint_hash: Sha256


class QuantityPath(TimeAwareModel):
    candidate_id: Identifier
    quantities_by_horizon: tuple[float, ...]


class ConstraintSlack(TimeAwareModel):
    constraint_name: Identifier
    slack: float


class SolutionValidationReport(TimeAwareModel):
    feasible: bool
    objective_value: float | None
    maximum_inequality_violation: float | None = Field(default=None, ge=0)
    maximum_equality_violation: float | None = Field(default=None, ge=0)
    slacks: tuple[ConstraintSlack, ...] = ()
    reason_codes: tuple[Identifier, ...] = ()


class ContinuousTargetSolution(TimeAwareModel):
    status: SolverStatus
    quantities: tuple[QuantityPath, ...]
    objective_value: float | None
    solver_name: Identifier
    solver_version: Identifier
    iterations: int | None = Field(default=None, ge=0)
    message: str
    solution_hash: Sha256
    validation: SolutionValidationReport


class RobustComparisonReport(TimeAwareModel):
    state: ComparisonState
    maximum_quantity_difference: float = Field(ge=0)
    nominal_objective: float | None
    robust_objective: float | None
    input_hashes_equal: bool
    execution_capability: bool = False
    reason_codes: tuple[Identifier, ...] = ()


class RobustTargetSolution(TimeAwareModel):
    solution: ContinuousTargetSolution | None
    comparison: RobustComparisonReport


class RoundingChange(TimeAwareModel):
    candidate_id: Identifier
    horizon_id: Identifier
    continuous_quantity: float
    discrete_quantity: float


class DiscreteTargetPositionPanel(TimeAwareModel):
    status: DiscreteStatus
    quantities: tuple[QuantityPath, ...]
    changes: tuple[RoundingChange, ...]
    objective_value: float | None
    validation: SolutionValidationReport
    discrete_hash: Sha256
    reason_codes: tuple[Identifier, ...] = ()


class MarginalTradeBenefitReport(TimeAwareModel):
    hold_objective: float | None
    target_objective: float | None
    objective_improvement: float
    total_first_action_quantity_change: float = Field(ge=0)


class RebalanceDecisionPanel(TimeAwareModel):
    action: RebalanceAction
    benefit: MarginalTradeBenefitReport
    reason_codes: tuple[Identifier, ...]


class TargetAction(TimeAwareModel):
    candidate_id: Identifier
    current_quantity: float
    target_quantity: float
    delta_quantity: float


class MPCControlPlan(TimeAwareModel):
    decision_snapshot_hash: Sha256
    action: RebalanceAction
    first_actions: tuple[TargetAction, ...]
    future_plan: tuple[QuantityPath, ...]
    valid_from: datetime
    valid_until: datetime
    reoptimization_triggers: tuple[Identifier, ...]
    first_action_only: bool = True
    plan_hash: Sha256


class S5ResultPayload(TimeAwareModel):
    compiled_objective: CompiledPortfolioObjective
    compiled_constraints: CompiledConstraintSet
    nominal_solution: ContinuousTargetSolution
    robust_shadow: RobustTargetSolution
    discrete_target: DiscreteTargetPositionPanel
    rebalance_decision: RebalanceDecisionPanel
    mpc_plan: MPCControlPlan
    module_receipts: tuple[Identifier, ...]


class S5ResultBundle(TimeAwareModel):
    envelope: ArtifactEnvelope
    payload: S5ResultPayload
