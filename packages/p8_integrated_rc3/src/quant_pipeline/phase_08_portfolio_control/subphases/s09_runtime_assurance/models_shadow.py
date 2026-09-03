from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from .enums import ComparisonState, ReasonCode
from .models_common import RuntimeContext, StrictModel, TargetQuantity


class PolicyDecision(StrictModel):
    policy_id: str = Field(min_length=1)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenario_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    constraint_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: str = Field(min_length=1)
    targets: tuple[TargetQuantity, ...]
    predicted_risk: Decimal = Field(ge=0)
    risk_limit: Decimal = Field(gt=0)


class ChampionDecision(PolicyDecision):
    execution_authority: Literal[True] = True


class ChallengerDecision(PolicyDecision):
    execution_authority: Literal[False] = False


class ShadowEvaluationPolicy(StrictModel):
    benign_quantity_tolerance: Decimal = Field(ge=0)
    material_quantity_tolerance: Decimal = Field(gt=0)
    risk_tolerance: Decimal = Field(ge=0)


class ShadowEvaluationRequest(StrictModel):
    context: RuntimeContext
    champion: ChampionDecision
    challenger: ChallengerDecision
    policy: ShadowEvaluationPolicy


class ShadowEvaluationResult(StrictModel):
    comparison_state: ComparisonState
    action_agrees: bool
    max_absolute_quantity_difference: Decimal
    absolute_risk_difference: Decimal
    reason_codes: tuple[ReasonCode, ...]
    challenger_execution_authority: Literal[False] = False
