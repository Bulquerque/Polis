from __future__ import annotations

from ..contracts.canonicalization import canonical_sha256
from ..errors import ObjectiveSemanticError
from ..models.artifacts import CompiledPortfolioObjective, ObjectiveComponent
from ..models.enums import ScoreSemantics
from ..models.inputs import DecisionReadyRiskPayload
from .arrays import payload_to_arrays


def compile_objective(payload: DecisionReadyRiskPayload) -> CompiledPortfolioObjective:
    policy = payload.policy_context.objective
    if policy.return_weight < 0:
        raise ObjectiveSemanticError("return weight must be non-negative")
    arrays = payload_to_arrays(payload)
    if len(payload.scenarios):
        expected = (arrays.probabilities[:, None, None] * arrays.scenario_pnl).sum(axis=0)
    else:
        expected = arrays.scenario_pnl.sum(axis=0)
    components = (
        ObjectiveComponent(component_id="EXPECTED_SCENARIO_PNL", component_type="RETURN", weight=policy.return_weight, unit="CURRENCY", direction="MAXIMIZE"),
        ObjectiveComponent(component_id="CVAR", component_type="TAIL_RISK", weight=policy.cvar_weight, unit="CURRENCY", direction="MINIMIZE"),
        ObjectiveComponent(component_id="TRANSACTION_COST", component_type="COST", weight=policy.transaction_cost_weight, unit="CURRENCY", direction="MINIMIZE"),
        ObjectiveComponent(component_id="TURNOVER", component_type="TURNOVER", weight=policy.turnover_weight, unit="QUANTITY", direction="MINIMIZE"),
        ObjectiveComponent(component_id="FUNDING", component_type="COST", weight=policy.funding_weight, unit="CURRENCY", direction="MINIMIZE"),
        ObjectiveComponent(component_id="ORDINAL_INVERSION", component_type="ORDINAL", weight=policy.ordinal_penalty_weight, unit="DIMENSIONLESS", direction="MINIMIZE"),
    )
    draft = CompiledPortfolioObjective(
        candidate_ids=arrays.candidate_ids,
        horizon_ids=arrays.horizon_ids,
        expected_pnl_by_horizon_candidate=tuple(tuple(float(x) for x in row) for row in expected),
        transaction_cost_by_candidate=tuple(float(x) for x in arrays.transaction_cost),
        funding_cost_by_horizon_candidate=tuple(tuple(float(x) for x in row) for row in arrays.funding),
        components=components,
        ordinal_penalty_count=len(payload.ordinal_preferences),
        objective_hash="0" * 64,
    )
    return draft.model_copy(update={"objective_hash": canonical_sha256(draft.model_copy(update={"objective_hash": "0" * 64}))})

