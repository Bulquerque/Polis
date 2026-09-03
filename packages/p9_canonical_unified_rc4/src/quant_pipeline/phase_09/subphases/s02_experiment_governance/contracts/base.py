from __future__ import annotations

from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import StringConstraints

from quant_pipeline.phase_09.contracts.base import (
    ArtifactId,
    Availability,
    CycleId,
    ModuleId,
    ModuleStatus,
    NonEmptyStr,
    ReasonCode,
    RunId,
    SemanticVersion,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)

ExperimentId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^exp-[a-z0-9][a-z0-9._-]{2,127}$"),
]
ConfigurationId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^cfg-[0-9a-f]{64}$"),
]
TrialId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^trial-[0-9a-f]{64}$"),
]
ParameterId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^P[5-8]\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"),
]
MetricId: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{2,127}$"),
]
DatasetId: TypeAlias = NonEmptyStr
CapabilityId: TypeAlias = NonEmptyStr


class MetricDirection(StrEnum):
    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


class CapabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    RESERVED = "RESERVED"
    UNAVAILABLE = "UNAVAILABLE"


class SearchStrategy(StrEnum):
    GRID = "GRID"
    RANDOM = "RANDOM"
    SUCCESSIVE_HALVING = "SUCCESSIVE_HALVING"
    HYPERBAND = "HYPERBAND"
    BOHB = "BOHB"


class ParameterKind(StrEnum):
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    CATEGORICAL = "CATEGORICAL"
    BOOLEAN = "BOOLEAN"


class ParameterScale(StrEnum):
    LINEAR = "LINEAR"
    LOG = "LOG"


class ConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"


class TrialState(StrEnum):
    PLANNED = "PLANNED"
    RESERVED = "RESERVED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INVALID = "INVALID"
    INFEASIBLE = "INFEASIBLE"
    EARLY_STOPPED = "EARLY_STOPPED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    CANCELLED_UPSTREAM = "CANCELLED_UPSTREAM"


class ExperimentValidationState(StrEnum):
    SPEC_VALID = "SPEC_VALID"
    SPEC_VALID_WITH_LIMITATIONS = "SPEC_VALID_WITH_LIMITATIONS"
    SPEC_INVALID = "SPEC_INVALID"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    HOLDOUT_POLICY_INVALID = "HOLDOUT_POLICY_INVALID"


class RegistryState(StrEnum):
    REGISTRY_SNAPSHOT_READY = "REGISTRY_SNAPSHOT_READY"
    REGISTRY_LIMITED = "REGISTRY_LIMITED"
    PARAMETER_SCHEMA_INCOMPATIBLE = "PARAMETER_SCHEMA_INCOMPATIBLE"
    PARAMETER_DEPRECATED_BLOCKING = "PARAMETER_DEPRECATED_BLOCKING"


class SearchSpaceState(StrEnum):
    SPACE_COMPILED = "SPACE_COMPILED"
    SPACE_COMPILED_WITH_WARNINGS = "SPACE_COMPILED_WITH_WARNINGS"
    SPACE_EMPTY = "SPACE_EMPTY"
    SPACE_EXPLOSIVE = "SPACE_EXPLOSIVE"
    SPACE_INVALID = "SPACE_INVALID"


class BudgetState(StrEnum):
    BUDGET_RESERVED = "BUDGET_RESERVED"
    BUDGET_LIMITED = "BUDGET_LIMITED"
    BUDGET_INFEASIBLE = "BUDGET_INFEASIBLE"
    RESOURCE_CAPABILITY_UNAVAILABLE = "RESOURCE_CAPABILITY_UNAVAILABLE"


class CatalogState(StrEnum):
    CATALOG_READY = "CATALOG_READY"
    CATALOG_WITH_EQUIVALENCES = "CATALOG_WITH_EQUIVALENCES"
    IDENTITY_COLLISION = "IDENTITY_COLLISION"
    LINEAGE_INVALID = "LINEAGE_INVALID"


class TrialPlanState(StrEnum):
    PLAN_READY = "PLAN_READY"
    PLAN_READY_LIMITED = "PLAN_READY_LIMITED"
    NO_TRIALS_VALID = "NO_TRIALS_VALID"
    SCHEDULER_INFEASIBLE = "SCHEDULER_INFEASIBLE"
    BUNDLE_INVALID = "BUNDLE_INVALID"


__all__ = [
    "ArtifactId",
    "Availability",
    "BudgetState",
    "CapabilityId",
    "CapabilityState",
    "CatalogState",
    "ConditionOperator",
    "ConfigurationId",
    "CycleId",
    "DatasetId",
    "ExperimentId",
    "ExperimentValidationState",
    "MetricDirection",
    "MetricId",
    "ModuleId",
    "ModuleStatus",
    "NonEmptyStr",
    "ParameterId",
    "ParameterKind",
    "ParameterScale",
    "ReasonCode",
    "RegistryState",
    "RunId",
    "SearchSpaceState",
    "SearchStrategy",
    "SemanticVersion",
    "Sha256Hex",
    "StrictModel",
    "TrialId",
    "TrialPlanState",
    "TrialState",
    "UtcDateTime",
]
