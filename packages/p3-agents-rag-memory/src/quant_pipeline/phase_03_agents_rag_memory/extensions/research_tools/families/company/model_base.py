"""Shared contracts and identifiers for P3.S38."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import (
    ContractModel, NonEmptyStr, Sha256, content_hash, utc,
)

SCHEMA_VERSION = "p3.s38.v1"
TOOL_ID = "company.fundamentals.v1"
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
PositiveInt = Annotated[int, Field(gt=0)]


class CompanyMode(StrEnum):
    QUICK_CHECK = "QUICK_CHECK"
    STANDARD_REVIEW = "STANDARD_REVIEW"
    DEEP_QUALITATIVE = "DEEP_QUALITATIVE"
    ACCOUNTING_QUALITY = "ACCOUNTING_QUALITY"
    FORENSIC = "FORENSIC"


class QualificationStatus(StrEnum):
    QUALIFIED_LOCAL = "QUALIFIED_LOCAL"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAILED = "FAILED"


class ReadinessStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class OutcomeStatus(StrEnum):
    PASS = "PASS"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class ValuationMethod(StrEnum):
    OBSERVED_MULTIPLES = "OBSERVED_MULTIPLES"
    HISTORICAL_BAND = "HISTORICAL_BAND"
    PEER_BAND = "PEER_BAND"
    SCENARIO_DCF = "SCENARIO_DCF"
    REVERSE_DCF = "REVERSE_DCF"


class ExtensionLineage(ContractModel):
    lineage_id: NonEmptyStr
    producer_module_id: Annotated[str, Field(pattern=r"^P3\.S38\.M\d{2}$")]
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: dict[NonEmptyStr, Sha256] = Field(default_factory=dict)
    transformation_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def hashes_reference_declared_sources(self) -> "ExtensionLineage":
        undeclared = set(self.source_hashes) - set(self.source_artifact_ids)
        if undeclared:
            raise ValueError(f"source hashes reference undeclared artifacts: {sorted(undeclared)}")
        return self


class CompanyCallContext(ContractModel):
    request_id: NonEmptyStr
    person_id: NonEmptyStr
    decision_time: datetime
    snapshot_id: NonEmptyStr
    deterministic_seed: NonNegativeInt = 0

    @field_validator("decision_time")
    @classmethod
    def aware_decision_time(cls, value: datetime) -> datetime:
        return utc(value)


def hashed_payload(value: object) -> str:
    return content_hash(value)
