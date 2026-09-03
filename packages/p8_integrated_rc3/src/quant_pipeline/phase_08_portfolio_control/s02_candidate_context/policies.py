
"""Immutable S2 policy objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from quant_pipeline.phase_08_contracts.enums import ComponentQualificationStatus

from .contracts.enums import PairwiseMode


@dataclass(frozen=True, slots=True)
class EquivalencePolicy:
    require_same_comparison_group_for_hard_redundancy: bool = True
    require_same_canonical_candidate_id_for_hard_redundancy: bool = True
    require_same_p5_belief_for_hard_redundancy: bool = True


@dataclass(frozen=True, slots=True)
class StaticAdmissionPolicy:
    collapse_exact_redundancy: bool = False
    usable_payoff_statuses: frozenset[ComponentQualificationStatus] = frozenset(
        {ComponentQualificationStatus.QUALIFIED, ComponentQualificationStatus.DEGRADED}
    )
    usable_lifecycle_statuses: frozenset[ComponentQualificationStatus] = frozenset(
        {ComponentQualificationStatus.QUALIFIED, ComponentQualificationStatus.DEGRADED}
    )


@dataclass(frozen=True, slots=True)
class OrdinalPreferencePolicy:
    pairwise_mode: PairwiseMode = PairwiseMode.ADJACENT_TIERS


@dataclass(frozen=True, slots=True)
class S2Policy:
    equivalence: EquivalencePolicy = field(default_factory=EquivalencePolicy)
    static_admission: StaticAdmissionPolicy = field(default_factory=StaticAdmissionPolicy)
    ordinal: OrdinalPreferencePolicy = field(default_factory=OrdinalPreferencePolicy)
