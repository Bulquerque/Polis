from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX64 = r"^[a-f0-9]{64}$"
NonEmptyStr = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    """Strict, immutable and closed boundary model."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        populate_by_name=True,
    )


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def canonical_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ScenarioClass(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    HYPOTHETICAL_SCENARIO = "HYPOTHETICAL_SCENARIO"
    UNIVARIATE_SENSITIVITY = "UNIVARIATE_SENSITIVITY"
    MULTIVARIATE_STRESS = "MULTIVARIATE_STRESS"
    REVERSE_STRESS = "REVERSE_STRESS"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    MARGIN_STRESS = "MARGIN_STRESS"
    EXECUTION_STRESS = "EXECUTION_STRESS"
    MODEL_STRESS = "MODEL_STRESS"
    SYSTEMIC_STRESS = "SYSTEMIC_STRESS"


class EvidenceClass(StrEnum):
    OBSERVED_LIVE = "OBSERVED_LIVE"
    OBSERVED_HISTORICAL = "OBSERVED_HISTORICAL"
    TRANSLATED_FACTOR = "TRANSLATED_FACTOR"
    MODELLED = "MODELLED"
    PARAMETRIC = "PARAMETRIC"
    STRESS_EXTRAPOLATED = "STRESS_EXTRAPOLATED"
    UNAVAILABLE = "UNAVAILABLE"


class CapabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class ReplayMode(StrEnum):
    STATIC_EXPOSURE = "STATIC_EXPOSURE"
    FROZEN_DYNAMIC_POLICY = "FROZEN_DYNAMIC_POLICY"


class OutputSemantics(StrEnum):
    PNL = "PNL"
    LOSS = "LOSS"
    SCORE = "SCORE"
    PORTFOLIO_VALUE = "PORTFOLIO_VALUE"


class BreachDirection(StrEnum):
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"


class AmbiguityFamily(StrEnum):
    DISCRETE_SUPPORT_WASSERSTEIN_1 = "DISCRETE_SUPPORT_WASSERSTEIN_1"


class ReverseNorm(StrEnum):
    WEIGHTED_L2 = "WEIGHTED_L2"


class S6State(StrEnum):
    SUCCESS = "SUCCESS"
    COMMITTED = "COMMITTED"
    COMMITTED_WITH_COVERAGE_GAPS = "COMMITTED_WITH_COVERAGE_GAPS"
    DUPLICATE_REJECTED = "DUPLICATE_REJECTED"
    SUCCESS_WITH_MAPPING_LIMITATIONS = "SUCCESS_WITH_MAPPING_LIMITATIONS"
    MATERIAL_EXPOSURE_UNMAPPED = "MATERIAL_EXPOSURE_UNMAPPED"
    LOCAL_ONLY = "LOCAL_ONLY"
    EXTRAPOLATION_LIMITED = "EXTRAPOLATION_LIMITED"
    CONSTRAINT_DISCONTINUITY_FOUND = "CONSTRAINT_DISCONTINUITY_FOUND"
    QUALIFIED = "QUALIFIED"
    QUALIFIED_WITH_LIMITATIONS = "QUALIFIED_WITH_LIMITATIONS"
    INSUFFICIENT_EXCEEDANCES = "INSUFFICIENT_EXCEEDANCES"
    UNSTABLE_TAIL_INDEX = "UNSTABLE_TAIL_INDEX"
    THRESHOLD_NOT_IDENTIFIED = "THRESHOLD_NOT_IDENTIFIED"
    DEPENDENCE_NOT_REMOVED = "DEPENDENCE_NOT_REMOVED"
    AMBIGUITY_SET_UNINFORMATIVE = "AMBIGUITY_SET_UNINFORMATIVE"
    SOLVER_NOT_QUALIFIED = "SOLVER_NOT_QUALIFIED"
    UNBOUNDED = "UNBOUNDED"
    CAPACITY_LIMITED = "CAPACITY_LIMITED"
    BORROW_LIMITED = "BORROW_LIMITED"
    MARGIN_FRAGILE = "MARGIN_FRAGILE"
    NETWORK_STRESS_RESEARCH_ONLY = "NETWORK_STRESS_RESEARCH_ONLY"
    INSUFFICIENT_LIQUIDITY_DATA = "INSUFFICIENT_LIQUIDITY_DATA"
    STRESS_RESILIENT = "STRESS_RESILIENT"
    RESILIENT_WITH_LIMITATIONS = "RESILIENT_WITH_LIMITATIONS"
    REVERSE_STRESS_TOO_CLOSE = "REVERSE_STRESS_TOO_CLOSE"
    STRUCTURALLY_UNSAFE = "STRUCTURALLY_UNSAFE"
    NO_FAILURE_WITHIN_DOMAIN = "NO_FAILURE_WITHIN_DOMAIN"
    SEARCH_NOT_CONVERGED = "SEARCH_NOT_CONVERGED"
    VALIDATED = "VALIDATED"
    VALIDATED_WITH_LIMITATIONS = "VALIDATED_WITH_LIMITATIONS"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SCENARIO_INCOMPLETE = "SCENARIO_INCOMPLETE"
    MODEL_NOT_FIT_FOR_STRESS = "MODEL_NOT_FIT_FOR_STRESS"
    UNVALIDATED = "UNVALIDATED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID = "INVALID"


class RunContext(StrictModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    experiment_id: NonEmptyStr
    configuration_id: NonEmptyStr
    decision_time: datetime
    available_at: datetime
    code_sha256: Annotated[str, Field(pattern=HEX64)]
    data_sha256: Annotated[str, Field(pattern=HEX64)]

    @field_validator("decision_time", "available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def enforce_point_in_time(self) -> Self:
        if self.available_at > self.decision_time:
            raise ValueError("available_at must not exceed decision_time")
        return self


class EvidenceReference(StrictModel):
    evidence_id: NonEmptyStr
    evidence_type: NonEmptyStr
    content_sha256: Annotated[str, Field(pattern=HEX64)]
    evidence_class: EvidenceClass


class S5QualificationReference(StrictModel):
    bundle_id: NonEmptyStr
    bundle_sha256: Annotated[str, Field(pattern=HEX64)]
    qualification_status: NonEmptyStr
    source_version: NonEmptyStr = "0.1.0rc1"


class SeedPolicy(StrictModel):
    root_entropy: Annotated[int, Field(ge=0)]
    algorithm: NonEmptyStr = "PCG64"
    derivation_version: NonEmptyStr = "seedsequence-v1"


class ModuleReceipt(StrictModel):
    module_id: NonEmptyStr
    status: S6State
    reason_codes: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    output_sha256: Annotated[str, Field(pattern=HEX64)]
    started_at: datetime
    completed_at: datetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc_datetime(value)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self
