"""Deterministic Pareto-aware equivalence and QD archive selection."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import ArchiveMode
from ..domain.models import (
    ArchiveCoverageReport,
    CandidateEquivalence,
    CandidateRiskSummary,
    CostLiquidityRecord,
    QualityDiversityCell,
    StrategyCandidate,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import canonical_sha256

ZERO = Decimal("0")
ONE = Decimal("1")
INF = Decimal("Infinity")


def select_representatives(
    candidates: tuple[StrategyCandidate, ...],
    records: tuple[CandidateEquivalence, ...],
    risks: tuple[CandidateRiskSummary, ...],
    costs: tuple[CostLiquidityRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[CandidateEquivalence, ...],
    tuple[StrategyCandidate, ...],
    tuple[QualityDiversityCell, ...],
]:
    candidate_by_id = {item.candidate_id: item for item in candidates}
    risk_by_id = {item.candidate_id: item for item in risks}
    cost_by_id = {item.candidate_id: item for item in costs}
    chosen = _choose_cluster_representatives(
        records, candidate_by_id, risk_by_id, cost_by_id
    )
    updated = tuple(
        item.model_copy(update={"representative": item.candidate_id in chosen})
        for item in records
    )
    representatives = tuple(candidate_by_id[cid] for cid in sorted(chosen))
    cells, published_ids = _build_archive(
        representatives, risk_by_id, cost_by_id, configuration
    )
    ordered_published = _global_budget_order(
        published_ids, candidate_by_id, risk_by_id, cost_by_id
    )
    published = tuple(candidate_by_id[cid] for cid in ordered_published)[
        : configuration.budgets.max_candidates_published
    ]
    return updated, published, cells


def archive_coverage_report(
    cells: tuple[QualityDiversityCell, ...],
    candidates: tuple[StrategyCandidate, ...],
    duplicate_count: int,
    configuration: Phase6RunConfiguration,
) -> ArchiveCoverageReport:
    underlyings = {item.underlying_id for item in candidates}
    objectives = {item.objective_family for item in candidates}
    possible = max(1, len(underlyings) * len(objectives) * configuration.budgets.max_legs * 3)
    filled = len(cells)
    existing = {item.niche_id for item in cells}
    theoretical = tuple(
        f"{underlying}|{objective.value}|L{legs}|{bucket}"
        for underlying in sorted(underlyings)
        for objective in sorted(objectives, key=lambda item: item.value)
        for legs in range(1, configuration.budgets.max_legs + 1)
        for bucket in ("LOW", "MEDIUM", "HIGH")
    )
    empty = tuple(item for item in theoretical if item not in existing)[:100]
    coverage = min(ONE, Decimal(filled) / Decimal(possible))
    return ArchiveCoverageReport(
        archive_mode=configuration.publication.archive_mode.value,
        niches_defined=possible,
        niches_filled=filled,
        coverage=coverage,
        candidate_count=len(candidates),
        duplicate_count=max(duplicate_count, 0),
        empty_regions=empty,
        generation_saturated=len(candidates) >= configuration.budgets.max_candidates_published,
    )


def _choose_cluster_representatives(
    records: tuple[CandidateEquivalence, ...],
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> set[str]:
    clusters: dict[str, list[CandidateEquivalence]] = defaultdict(list)
    for item in records:
        clusters[item.equivalence_cluster_id].append(item)
    chosen: set[str] = set()
    for values in clusters.values():
        front = _pareto_front(
            tuple(item.candidate_id for item in values),
            candidate_by_id,
            risk_by_id,
            cost_by_id,
        )
        chosen.add(_quality_order(front, candidate_by_id, risk_by_id, cost_by_id)[0])
    return chosen


def _build_archive(
    representatives: tuple[StrategyCandidate, ...],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
    configuration: Phase6RunConfiguration,
) -> tuple[tuple[QualityDiversityCell, ...], set[str]]:
    niches: dict[str, list[str]] = defaultdict(list)
    for candidate in representatives:
        niche = _niche_id(
            candidate,
            risk_by_id[candidate.candidate_id],
            cost_by_id[candidate.candidate_id],
            configuration.publication.archive_mode,
        )
        niches[niche].append(candidate.candidate_id)
    candidate_by_id = {item.candidate_id: item for item in representatives}
    return _archive_cells(
        niches, candidate_by_id, risk_by_id, cost_by_id, configuration
    )


def _archive_cells(
    niches: dict[str, list[str]],
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
    configuration: Phase6RunConfiguration,
) -> tuple[tuple[QualityDiversityCell, ...], set[str]]:
    cells: list[QualityDiversityCell] = []
    published: set[str] = set()
    limit = configuration.publication.representatives_per_niche
    for niche, candidate_ids in sorted(niches.items()):
        front = _pareto_front(
            tuple(candidate_ids), candidate_by_id, risk_by_id, cost_by_id
        )
        selected = _diverse_selection(
            front,
            limit,
            candidate_by_id,
            risk_by_id,
            cost_by_id,
        )
        published.update(selected)
        first = candidate_by_id[selected[0]]
        cells.append(
            QualityDiversityCell(
                niche_id=niche,
                objective_family=first.objective_family,
                leg_count=len(first.legs),
                risk_bucket=niche.rsplit("|", 1)[-1],
                candidate_ids=tuple(sorted(candidate_ids)),
                representative_candidate_ids=selected,
            )
        )
    return tuple(cells), published


def _pareto_front(
    candidate_ids: tuple[str, ...],
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> tuple[str, ...]:
    front: list[str] = []
    vectors = {
        cid: _quality_vector(cid, candidate_by_id, risk_by_id, cost_by_id)
        for cid in candidate_ids
    }
    for cid in sorted(candidate_ids):
        vector = vectors[cid]
        dominated = any(
            other != cid and _dominates(vectors[other], vector)
            for other in candidate_ids
        )
        if not dominated:
            front.append(cid)
    return tuple(front or sorted(candidate_ids))


def _quality_vector(
    candidate_id: str,
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    candidate = candidate_by_id[candidate_id]
    risk = risk_by_id[candidate_id]
    cost = cost_by_id[candidate_id]
    max_loss = risk.maximum_loss if risk.maximum_loss is not None else INF
    spread = cost.maximum_relative_spread if cost.maximum_relative_spread is not None else INF
    liquidity = cost.weakest_leg_liquidity if cost.weakest_leg_liquidity is not None else ZERO
    return (
        Decimal(len(candidate.legs)),
        abs(cost.conservative_entry_cost),
        max_loss,
        spread,
        -liquidity,
    )


def _dominates(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> bool:
    return all(a <= b for a, b in zip(left, right)) and any(
        a < b for a, b in zip(left, right)
    )


def _quality_order(
    candidate_ids: tuple[str, ...] | set[str],
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            candidate_ids,
            key=lambda cid: (
                _quality_vector(cid, candidate_by_id, risk_by_id, cost_by_id),
                cid,
            ),
        )
    )


def _diverse_selection(
    candidate_ids: tuple[str, ...],
    limit: int,
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> tuple[str, ...]:
    ordered = list(
        _quality_order(candidate_ids, candidate_by_id, risk_by_id, cost_by_id)
    )
    if len(ordered) <= limit:
        return tuple(ordered)
    selected = [ordered.pop(0)]
    while ordered and len(selected) < limit:
        next_id = max(
            ordered,
            key=lambda cid: (
                min(
                    _leg_distance(candidate_by_id[cid], candidate_by_id[chosen])
                    for chosen in selected
                ),
                tuple(
                    -value if value.is_finite() else Decimal("-1e30")
                    for value in _quality_vector(
                        cid, candidate_by_id, risk_by_id, cost_by_id
                    )
                ),
                cid,
            ),
        )
        selected.append(next_id)
        ordered.remove(next_id)
    return tuple(selected)


def _leg_distance(left: StrategyCandidate, right: StrategyCandidate) -> Decimal:
    left_ids = {item.instrument_id for item in left.legs}
    right_ids = {item.instrument_id for item in right.legs}
    union = left_ids | right_ids
    if not union:
        return ZERO
    overlap = left_ids & right_ids
    return ONE - (Decimal(len(overlap)) / Decimal(len(union)))


def _global_budget_order(
    candidate_ids: set[str],
    candidate_by_id: dict[str, StrategyCandidate],
    risk_by_id: dict[str, CandidateRiskSummary],
    cost_by_id: dict[str, CostLiquidityRecord],
) -> tuple[str, ...]:
    return _quality_order(candidate_ids, candidate_by_id, risk_by_id, cost_by_id)


def _niche_id(
    candidate: StrategyCandidate,
    risk: CandidateRiskSummary,
    cost: CostLiquidityRecord,
    mode: ArchiveMode,
) -> str:
    base = abs(cost.conservative_entry_cost) or ONE
    ratio = risk.maximum_loss / base if risk.maximum_loss is not None else Decimal("999")
    bucket = _risk_bucket(ratio)
    descriptors = (
        candidate.underlying_id,
        candidate.objective_family.value,
        f"L{len(candidate.legs)}",
        bucket,
        candidate.origin_mode.value,
    )
    if mode is ArchiveMode.CLUSTER_ARCHIVE:
        return "CLUSTER|" + "|".join(descriptors)
    if mode is ArchiveMode.CVT_ARCHIVE:
        return "CVT|" + canonical_sha256(descriptors)[:4]
    return "|".join(descriptors[:4])


def _risk_bucket(ratio: Decimal) -> str:
    if ratio <= ONE:
        return "LOW"
    if ratio <= Decimal("3"):
        return "MEDIUM"
    return "HIGH"
