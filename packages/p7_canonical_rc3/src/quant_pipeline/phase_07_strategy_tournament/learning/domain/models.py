from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class Direction(StrEnum):
    HIGHER_BETTER = "HIGHER_BETTER"
    LOWER_BETTER = "LOWER_BETTER"


class Transformation(StrEnum):
    IDENTITY = "IDENTITY"
    NEGATE = "NEGATE"
    REGRET_TO_BEST = "REGRET_TO_BEST"


class SplitName(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    CALIBRATION = "CALIBRATION"
    TEST = "TEST"


class QualificationStatus(StrEnum):
    CHAMPION = "CHAMPION"
    QUALIFIED_CHALLENGER = "QUALIFIED_CHALLENGER"
    SHADOW = "SHADOW"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True, slots=True)
class TargetPolicy:
    target_id: str
    source_field: str
    unit: str
    raw_direction: Direction
    denominator: str
    transformation: Transformation
    utility_multiplier: float
    availability_field: str
    label_end_field: str
    policy_version: str
    costs_included: bool


@dataclass(frozen=True, slots=True)
class TrainingRow:
    candidate_id: str
    query_id: str
    cycle_id: str
    decision_time: datetime
    label_end_time: datetime
    outcome_available_at: datetime
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    feature_schema_version: str
    features: Mapping[str, float | None]
    interpretable_score: float
    utility_label: float
    selected_by_p8: bool
    candidate_topology: str
    regime: str | None
    lineage_id: str


@dataclass(frozen=True, slots=True)
class TemporalFold:
    fold_id: str
    train_query_ids: tuple[str, ...]
    validation_query_ids: tuple[str, ...]
    calibration_query_ids: tuple[str, ...]
    sealed_test_query_ids: tuple[str, ...]
    purged_query_ids: tuple[str, ...]
    embargoed_query_ids: tuple[str, ...]
    validation_start: datetime
    calibration_start: datetime
    test_start: datetime
