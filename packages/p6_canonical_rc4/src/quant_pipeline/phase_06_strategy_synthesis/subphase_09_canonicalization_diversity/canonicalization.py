"""Canonical legs, fingerprints, and equivalence clusters."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import Side
from ..domain.identity import candidate_id as build_candidate_id, shape_fingerprint, signed_quantity
from ..domain.models import (
    CandidateEquivalence,
    CandidateQualification,
    CandidateRiskSummary,
    CostLiquidityRecord,
    StrategyCandidate,
    StrategyLeg,
    StrategyPayoffRecord,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import canonical_sha256, stable_id

ZERO = Decimal("0")
ONE = Decimal("1")
LegKey = tuple[str, str, str, str]


def canonicalize_candidates(
    candidates: tuple[StrategyCandidate, ...],
    qualifications: tuple[CandidateQualification, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[StrategyCandidate, ...]:
    """Compatibility facade returning only canonical candidates."""
    records, _ = canonicalize_candidates_with_remap(candidates, qualifications, configuration)
    return records


def canonicalize_candidates_with_remap(
    candidates: tuple[StrategyCandidate, ...],
    qualifications: tuple[CandidateQualification, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[tuple[StrategyCandidate, ...], dict[str, str]]:
    """Canonicalize qualified candidates and bind identity to the final legs."""
    qualified_ids = {
        item.candidate_id
        for item in qualifications
        if item.qualified
    }
    output = []
    remap: dict[str, str] = {}
    for candidate in candidates:
        if candidate.candidate_id not in qualified_ids:
            continue
        legs = canonical_legs(candidate.legs)
        if not legs:
            continue
        final_candidate_id = build_candidate_id(
            underlying_id=candidate.underlying_id,
            decision_time=candidate.decision_time.isoformat(),
            legs=legs,
            objective_family=candidate.objective_family.value,
            policy_version=configuration.strategy.policy_version,
            horizon_days=candidate.horizon_days,
        )
        remap[candidate.candidate_id] = final_candidate_id
        output.append(
            candidate.model_copy(
                update={
                    "candidate_id": final_candidate_id,
                    "legs": legs,
                    "lineage_id": stable_id(
                        "canonical-lineage",
                        candidate.lineage_id,
                        candidate.candidate_id,
                        final_candidate_id,
                    ),
                }
            )
        )
    return tuple(output), remap


def canonical_legs(
    legs: tuple[StrategyLeg, ...],
) -> tuple[StrategyLeg, ...]:
    """Aggregate identical legs and remove exact cancellations."""
    grouped: dict[LegKey, Decimal] = defaultdict(Decimal)
    exemplar: dict[LegKey, StrategyLeg] = {}
    for leg in legs:
        key = _leg_key(leg)
        grouped[key] += signed_quantity(leg)
        exemplar[key] = leg
    canonical = []
    for key, quantity in sorted(grouped.items()):
        if quantity == ZERO:
            continue
        base = exemplar[key]
        canonical.append(
            base.model_copy(
                update={
                    "side": Side.LONG if quantity > ZERO else Side.SHORT,
                    "quantity": abs(quantity),
                }
            )
        )
    return tuple(canonical)


def relative_scale_records(
    candidates: tuple[StrategyCandidate, ...],
) -> tuple[CandidateEquivalence, ...]:
    records = []
    for candidate in candidates:
        leg_shape, scale = shape_fingerprint(candidate)
        records.append(
            CandidateEquivalence(
                candidate_id=candidate.candidate_id,
                leg_shape_fingerprint=leg_shape,
                payoff_fingerprint="PENDING",
                economic_fingerprint="PENDING",
                equivalence_cluster_id="PENDING",
                relative_scale=scale,
            )
        )
    return tuple(records)


def add_payoff_fingerprints(
    records: tuple[CandidateEquivalence, ...],
    payoffs: tuple[StrategyPayoffRecord, ...],
    candidates: tuple[StrategyCandidate, ...],
) -> tuple[CandidateEquivalence, ...]:
    payoff_by_id = {item.candidate_id: item for item in payoffs}
    candidate_by_id = {item.candidate_id: item for item in candidates}
    output = []
    for item in records:
        payoff = payoff_by_id[item.candidate_id]
        scale = item.relative_scale if item.relative_scale != ZERO else ONE
        normalized = tuple(value / scale for value in payoff.terminal_pnl)
        candidate = candidate_by_id[item.candidate_id]
        fingerprint = canonical_sha256(
            {
                "underlying_id": candidate.underlying_id,
                "spots": payoff.spot_grid,
                "pnl": normalized,
            }
        )
        output.append(
            item.model_copy(update={"payoff_fingerprint": fingerprint})
        )
    return tuple(output)


def add_economic_fingerprints(
    records: tuple[CandidateEquivalence, ...],
    risks: tuple[CandidateRiskSummary, ...],
    costs: tuple[CostLiquidityRecord, ...],
) -> tuple[CandidateEquivalence, ...]:
    risk_by_id = {item.candidate_id: item for item in risks}
    cost_by_id = {item.candidate_id: item for item in costs}
    output = []
    for item in records:
        risk = risk_by_id[item.candidate_id]
        cost = cost_by_id[item.candidate_id]
        fingerprint = canonical_sha256(
            {
                "payoff": item.payoff_fingerprint,
                "max_loss": risk.maximum_loss,
                "expected": risk.expected_net_payoff,
                "cost": cost.conservative_entry_cost,
                "liquidity": cost.weakest_leg_liquidity,
            }
        )
        output.append(
            item.model_copy(update={"economic_fingerprint": fingerprint})
        )
    return tuple(output)


def cluster_equivalence(
    records: tuple[CandidateEquivalence, ...],
) -> tuple[CandidateEquivalence, ...]:
    return tuple(
        item.model_copy(
            update={
                "equivalence_cluster_id": stable_id(
                    "equivalence",
                    item.payoff_fingerprint,
                    item.economic_fingerprint,
                )
            }
        )
        for item in records
    )


def _leg_key(leg: StrategyLeg) -> LegKey:
    return (
        leg.instrument_id,
        leg.instrument_type.value,
        "" if leg.strike is None else str(leg.strike),
        leg.expiration.isoformat() if leg.expiration else "",
    )
