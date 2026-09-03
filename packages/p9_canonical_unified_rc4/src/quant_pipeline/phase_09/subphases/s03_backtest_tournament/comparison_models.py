"""Contracts for conservative provisional comparison and model sets."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from .common import FiniteDecimal, NonEmptyStr, Sha256, StrictModel
from .scoring_models import ComparisonLossRecord, ConfigurationScoreAggregate


class ConfigurationLineage(StrictModel):
    configuration_id: NonEmptyStr
    economic_fingerprint: Sha256
    parent_configuration_id: NonEmptyStr | None = None


class ComparisonPolicy(StrictModel):
    policy_id: NonEmptyStr
    mean_loss_tolerance: FiniteDecimal = Field(default=Decimal("0"), ge=Decimal("0"))
    dominance_tolerance: FiniteDecimal = Field(default=Decimal("0"), ge=Decimal("0"))
    minimum_common_units: int = Field(default=2, ge=1)


class PairwiseComparison(StrictModel):
    configuration_a: NonEmptyStr
    configuration_b: NonEmptyStr
    common_unit_count: int = Field(ge=0)
    mean_loss_a: FiniteDecimal | None
    mean_loss_b: FiniteDecimal | None
    a_dominates_b: bool
    b_dominates_a: bool
    comparable: bool


class EquivalenceGroup(StrictModel):
    economic_fingerprint: Sha256
    configuration_ids: tuple[NonEmptyStr, ...]


class ProvisionalModelConfidenceSet(StrictModel):
    policy_id: NonEmptyStr
    cohort_id: NonEmptyStr
    configuration_ids: tuple[NonEmptyStr, ...]
    provisional: bool = True
    limitation: NonEmptyStr = (
        "Requires P9.S5 dependent-bootstrap and multiple-testing qualification"
    )


class TrialComparisonResult(StrictModel):
    policy_id: NonEmptyStr
    cohort_id: NonEmptyStr
    pairwise: tuple[PairwiseComparison, ...]
    equivalence_groups: tuple[EquivalenceGroup, ...]
    non_dominated_configuration_ids: tuple[NonEmptyStr, ...]
    provisional_model_set: ProvisionalModelConfidenceSet
    reason_codes: tuple[NonEmptyStr, ...]
    content_sha256: Sha256
