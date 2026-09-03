"""Immutable S8 domain values."""
from __future__ import annotations

from dataclasses import dataclass

from ..boundary.inputs import ComparisonGroupRecord, StrategyReferenceRecord
from ..boundary.outputs import DiversityClusterRecord, RankableRecord


@dataclass(frozen=True, slots=True)
class RankingCandidate:
    rankable: RankableRecord
    group: ComparisonGroupRecord
    strategy: StrategyReferenceRecord
    cluster: DiversityClusterRecord
