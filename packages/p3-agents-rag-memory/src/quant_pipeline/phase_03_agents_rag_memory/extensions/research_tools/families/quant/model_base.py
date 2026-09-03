"""Shared identifiers, enums, lineage, and call context for P3.S39."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import (
    ContractModel,
    NonEmptyStr,
    Sha256,
    content_hash,
    utc,
)

SCHEMA_VERSION = "p3.s39.v1"
TOOL_ID = "quant.diagnostics.v1"
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class QuantMode(StrEnum):
    BASIC = "BASIC"
    ROBUST = "ROBUST"
    STABILITY = "STABILITY"


class QualificationStatus(StrEnum):
    QUALIFIED_LOCAL = "QUALIFIED_LOCAL"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
    FAILED = "FAILED"


class OutcomeStatus(StrEnum):
    PASS = "PASS"
    EMPTY_VALID = "EMPTY_VALID"
    DEGRADED = "DEGRADED"
    BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"


class ReturnKind(StrEnum):
    SIMPLE = "SIMPLE"
    LOG = "LOG"


class VolatilityEstimator(StrEnum):
    CLOSE_TO_CLOSE = "CLOSE_TO_CLOSE"
    PARKINSON = "PARKINSON"
    GARMAN_KLASS = "GARMAN_KLASS"


class CorrelationMethod(StrEnum):
    PEARSON = "PEARSON"
    SPEARMAN = "SPEARMAN"


class EntropyMethod(StrEnum):
    SHANNON = "SHANNON"
    PERMUTATION = "PERMUTATION"


class BinningPolicy(StrEnum):
    EQUAL_WIDTH = "EQUAL_WIDTH"
    EQUAL_FREQUENCY = "EQUAL_FREQUENCY"
    FIXED_EDGES = "FIXED_EDGES"


class EventAdjustment(StrEnum):
    NONE = "NONE"
    BENCHMARK = "BENCHMARK"


class ExtensionLineage(ContractModel):
    lineage_id: NonEmptyStr
    producer_module_id: Annotated[str, Field(pattern=r"^P3\.S(?:3[2-9]|40)\.M\d{2}$")]
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    source_hashes: dict[NonEmptyStr, Sha256] = Field(default_factory=dict)
    transformation_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def source_hashes_are_declared(self) -> "ExtensionLineage":
        undeclared = set(self.source_hashes) - set(self.source_artifact_ids)
        if undeclared:
            raise ValueError(f"source hashes reference undeclared artifacts: {sorted(undeclared)}")
        return self


class QuantCallContext(ContractModel):
    request_id: NonEmptyStr
    person_id: NonEmptyStr
    decision_time: datetime
    snapshot_id: NonEmptyStr
    deterministic_seed: NonNegativeInt = 0
    qualification_mode: bool = False

    @field_validator("decision_time")
    @classmethod
    def aware_decision_time(cls, value: datetime) -> datetime:
        return utc(value)


def hashed_payload(model: ContractModel | dict[str, object] | tuple[object, ...]) -> str:
    return content_hash(model)
