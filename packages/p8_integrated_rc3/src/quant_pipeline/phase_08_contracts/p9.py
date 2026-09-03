"""Typed P9 → P8 feedback, P9 recommendation, and P0 authorization contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self, Union

from pydantic import Field, TypeAdapter, model_validator

from .base import AwareDatetime, NonEmptyStr, SHA256Str, StrictModel
from .common import ArtifactReference
from .enums import FeedbackEffectType, FeedbackRecommendationStatus


class OptimizerEligibilityPayload(StrictModel):
    optimizer_id: NonEmptyStr
    enabled: bool


class RiskLimitPolicyPayload(StrictModel):
    limit_name: NonEmptyStr
    new_limit: Decimal
    unit: NonEmptyStr


class TurnoverPolicyPayload(StrictModel):
    max_turnover: Decimal = Field(ge=0)


class LiquidityHaircutPayload(StrictModel):
    instrument_family: NonEmptyStr
    haircut_ratio: Decimal = Field(ge=0, le=1)


class MarginBufferPayload(StrictModel):
    buffer_ratio: Decimal = Field(ge=0)


class ExecutionPolicyPayload(StrictModel):
    max_participation_rate: Decimal = Field(gt=0, le=1)
    allowed_order_types: tuple[NonEmptyStr, ...] = Field(min_length=1)


class RuntimeFallbackPolicyPayload(StrictModel):
    fallback_mode: NonEmptyStr
    trigger_threshold: Decimal = Field(ge=0)


class ModelDeprecationPayload(StrictModel):
    model_id: NonEmptyStr
    deprecated: Literal[True]
    reason: NonEmptyStr


class _FeedbackBase(StrictModel):
    feedback_id: NonEmptyStr
    contract_version: Literal["P9_TO_P8_PROMOTED_FEEDBACK_V1"]
    schema_version: Literal["1.0.0"]
    source_cycle_id: NonEmptyStr
    source_cycle_sequence: int = Field(ge=0, strict=True)
    target_cycle_id: NonEmptyStr
    target_cycle_sequence: int = Field(ge=0, strict=True)
    target_policy_id: NonEmptyStr
    p9_recommendation_ref: ArtifactReference
    p0_authorization_ref: ArtifactReference
    effective_from_sequence: int = Field(ge=0, strict=True)
    expires_after_sequence: int | None = Field(default=None, ge=0, strict=True)
    idempotency_key: NonEmptyStr
    available_at: AwareDatetime
    content_sha256: SHA256Str

    @model_validator(mode="after")
    def validate_cycle_order(self) -> Self:
        if self.source_cycle_sequence >= self.target_cycle_sequence:
            raise ValueError("feedback must target a later cycle")
        if self.effective_from_sequence < self.target_cycle_sequence:
            raise ValueError("effective_from_sequence cannot precede target cycle")
        if self.expires_after_sequence is not None and self.expires_after_sequence < self.effective_from_sequence:
            raise ValueError("feedback expiry cannot precede effective sequence")
        return self


class OptimizerEligibilityFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.OPTIMIZER_ELIGIBILITY_FEEDBACK]
    payload: OptimizerEligibilityPayload


class RiskLimitPolicyFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK]
    payload: RiskLimitPolicyPayload


class TurnoverPolicyFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.TURNOVER_POLICY_FEEDBACK]
    payload: TurnoverPolicyPayload


class LiquidityHaircutFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.LIQUIDITY_HAIRCUT_FEEDBACK]
    payload: LiquidityHaircutPayload


class MarginBufferFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.MARGIN_BUFFER_FEEDBACK]
    payload: MarginBufferPayload


class ExecutionPolicyFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.EXECUTION_POLICY_FEEDBACK]
    payload: ExecutionPolicyPayload


class RuntimeFallbackPolicyFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.RUNTIME_FALLBACK_POLICY_FEEDBACK]
    payload: RuntimeFallbackPolicyPayload


class ModelDeprecationFeedback(_FeedbackBase):
    effect_type: Literal[FeedbackEffectType.MODEL_DEPRECATION_FEEDBACK]
    payload: ModelDeprecationPayload


PromotedFeedback = Annotated[
    Union[
        OptimizerEligibilityFeedback,
        RiskLimitPolicyFeedback,
        TurnoverPolicyFeedback,
        LiquidityHaircutFeedback,
        MarginBufferFeedback,
        ExecutionPolicyFeedback,
        RuntimeFallbackPolicyFeedback,
        ModelDeprecationFeedback,
    ],
    Field(discriminator="effect_type"),
]
PROMOTED_FEEDBACK_ADAPTER = TypeAdapter(PromotedFeedback)


class NumericAuthorizationBound(StrictModel):
    field_name: NonEmptyStr
    minimum: Decimal | None = None
    maximum: Decimal | None = None

    @model_validator(mode="after")
    def validate_bound(self) -> Self:
        if self.minimum is None and self.maximum is None:
            raise ValueError("numeric bound requires minimum or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("numeric bound minimum exceeds maximum")
        return self


class AllowedValuesAuthorizationBound(StrictModel):
    field_name: NonEmptyStr
    allowed_values: tuple[NonEmptyStr, ...] = Field(min_length=1)


class P9FeedbackRecommendationV1(StrictModel):
    recommendation_id: NonEmptyStr
    feedback_id: NonEmptyStr
    target_policy_id: NonEmptyStr
    effect_type: FeedbackEffectType
    status: FeedbackRecommendationStatus
    source_cycle_sequence: int = Field(ge=0, strict=True)
    available_at: AwareDatetime


class P0PolicyAuthorizationV1(StrictModel):
    authorization_id: NonEmptyStr
    feedback_id: NonEmptyStr
    target_policy_id: NonEmptyStr
    effect_type: FeedbackEffectType
    valid_from_sequence: int = Field(ge=0, strict=True)
    expires_after_sequence: int | None = Field(default=None, ge=0, strict=True)
    numeric_bounds: tuple[NumericAuthorizationBound, ...] = Field(default_factory=tuple)
    allowed_values: tuple[AllowedValuesAuthorizationBound, ...] = Field(default_factory=tuple)
    available_at: AwareDatetime

    @model_validator(mode="after")
    def validate_authorization_window(self) -> Self:
        if self.expires_after_sequence is not None and self.expires_after_sequence < self.valid_from_sequence:
            raise ValueError("authorization expiry cannot precede valid_from_sequence")
        return self
