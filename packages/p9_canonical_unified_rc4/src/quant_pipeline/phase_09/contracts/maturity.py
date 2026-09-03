from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .base import FiniteDecimal, NonEmptyStr, ReasonCode, StrictModel, UtcDateTime
from .integrity import IntegrityEnvelope


class LifecycleStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    SETTLED = "SETTLED"
    DELISTED = "DELISTED"
    UNKNOWN = "UNKNOWN"


class MaturityBasis(StrEnum):
    HORIZON = "HORIZON"
    CLOSE = "CLOSE"
    EXPIRATION = "EXPIRATION"
    SETTLEMENT = "SETTLEMENT"


class MaturityState(StrEnum):
    NOT_MATURED = "NOT_MATURED"
    PARTIALLY_MATURED = "PARTIALLY_MATURED"
    MATURED = "MATURED"
    SETTLED = "SETTLED"
    CENSORED = "CENSORED"
    UNOBSERVABLE = "UNOBSERVABLE"


class MaturitySubject(StrictModel):
    subject_id: NonEmptyStr
    target_type: NonEmptyStr
    instrument_id: NonEmptyStr
    contract_key: NonEmptyStr
    decision_time: UtcDateTime
    horizon_end: UtcDateTime | None = None
    close_time: UtcDateTime | None = None
    expiration_time: UtcDateTime | None = None
    settlement_time: UtcDateTime | None = None
    observation_end: UtcDateTime | None = None
    data_available_at: UtcDateTime | None = None
    lifecycle_status: LifecycleStatus
    censoring_reason: NonEmptyStr | None = None
    reference_price: FiniteDecimal
    quantity: FiniteDecimal
    contract_multiplier: FiniteDecimal

    @model_validator(mode="after")
    def validate_subject(self) -> "MaturitySubject":
        for value in (
            self.horizon_end,
            self.close_time,
            self.expiration_time,
            self.settlement_time,
            self.observation_end,
        ):
            if value is not None and value < self.decision_time:
                raise ValueError("subject times cannot precede decision_time")
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive")
        return self


class MaturitySubjectManifestPayload(StrictModel):
    manifest_id: NonEmptyStr
    subjects: tuple[MaturitySubject, ...]

    @model_validator(mode="after")
    def validate_unique_subjects(self) -> "MaturitySubjectManifestPayload":
        ids = [subject.subject_id for subject in self.subjects]
        if len(ids) != len(set(ids)):
            raise ValueError("maturity subject IDs must be unique")
        return self


class MaturitySubjectManifest(StrictModel):
    payload: MaturitySubjectManifestPayload
    integrity: IntegrityEnvelope


class OutcomeMaturityPolicy(StrictModel):
    policy_id: NonEmptyStr
    metric_family: NonEmptyStr
    target_type: NonEmptyStr
    basis: MaturityBasis
    allow_partial: bool = False
    requires_observable_data: bool = True
    grace_period_seconds: int = Field(default=0, ge=0)


class OutcomeMaturityPolicyRegistry(StrictModel):
    policies: tuple[OutcomeMaturityPolicy, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "OutcomeMaturityPolicyRegistry":
        keys = [(policy.metric_family, policy.target_type) for policy in self.policies]
        if len(keys) != len(set(keys)):
            raise ValueError("maturity policies must be unique by metric_family/target_type")
        return self


class MaturityDecision(StrictModel):
    subject_id: NonEmptyStr
    metric_family: NonEmptyStr
    state: MaturityState
    required_at: UtcDateTime | None
    evaluation_as_of: UtcDateTime
    observable: bool
    eligible: bool
    reason_codes: tuple[ReasonCode, ...] = ()


class OutcomeMaturityPanel(StrictModel):
    decisions: tuple[MaturityDecision, ...]


class EvaluationEligibilityPanel(StrictModel):
    eligible_keys: tuple[NonEmptyStr, ...]
    ineligible_keys: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_disjoint(self) -> "EvaluationEligibilityPanel":
        eligible = set(self.eligible_keys)
        ineligible = set(self.ineligible_keys)
        if eligible & ineligible:
            raise ValueError("eligible and ineligible keys must be disjoint")
        return self


class MaturityDecisionTrace(StrictModel):
    evaluation_as_of: UtcDateTime
    policy_ids: tuple[NonEmptyStr, ...]
    decision_count: int = Field(ge=0)
