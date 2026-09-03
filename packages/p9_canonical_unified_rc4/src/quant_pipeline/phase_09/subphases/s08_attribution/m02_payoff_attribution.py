"""P9.S8.M02 — payoff fidelity, candidate coverage, and P6 estimate accuracy."""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class PayoffScenarioPoint(StrictModel):
    candidate_id: NonEmptyStr
    scenario_id: NonEmptyStr
    target_payoff_per_unit: float
    candidate_payoff_per_unit: float
    probability_weight: float = Field(gt=0.0)


class CandidateOutcome(StrictModel):
    candidate_id: NonEmptyStr
    selected_by_p6: bool
    observable: bool
    realized_unit_pnl: float | None = None
    estimated_price: float | None = None
    actual_price: float | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    estimated_liquidity: float | None = None
    actual_liquidity: float | None = None
    estimated_risk: float | None = None
    actual_risk: float | None = None
    maximum_loss_bound: float | None = Field(default=None, ge=0.0)
    observed_loss: float | None = Field(default=None, ge=0.0)
    evidence_class: EvidenceClass

    @model_validator(mode="after")
    def validate_pairs(self) -> "CandidateOutcome":
        pairs = (
            (self.estimated_price, self.actual_price),
            (self.estimated_cost, self.actual_cost),
            (self.estimated_liquidity, self.actual_liquidity),
            (self.estimated_risk, self.actual_risk),
        )
        if any((left is None) != (right is None) for left, right in pairs):
            raise ValueError("estimate and actual must be provided together")
        return self


class PayoffAttributionPolicy(StrictModel):
    minimum_scenarios: int = Field(default=3, ge=1)
    fidelity_tolerance: float = Field(default=0.25, ge=0.0)
    require_observable_regret: bool = True


class PayoffFidelityItem(StrictModel):
    candidate_id: NonEmptyStr
    scenario_count: int = Field(ge=0)
    weighted_mae: float | None
    weighted_rmse: float | None
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...] = ()


class EstimateAccuracyItem(StrictModel):
    candidate_id: NonEmptyStr
    price_error: float | None = None
    cost_error: float | None = None
    liquidity_error: float | None = None
    risk_error: float | None = None
    maximum_loss_proof_valid: bool | None = None
    evidence_class: EvidenceClass


class PayoffAttributionResult(StrictModel):
    fidelity: tuple[PayoffFidelityItem, ...]
    estimates: tuple[EstimateAccuracyItem, ...]
    candidate_count: int = Field(ge=0)
    observable_candidate_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    selected_candidate_id: NonEmptyStr | None
    best_observable_candidate_id: NonEmptyStr | None
    synthesis_regret: float | None
    aggregate_pnl_effect: float | None
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evaluate_payoff_fidelity(
    scenario_points: tuple[PayoffScenarioPoint, ...],
    outcomes: tuple[CandidateOutcome, ...],
    policy: PayoffAttributionPolicy,
) -> PayoffAttributionResult:
    """Evaluate P6 shape fidelity, estimate errors, coverage, and synthesis regret."""

    by_candidate: dict[str, list[PayoffScenarioPoint]] = defaultdict(list)
    for point in scenario_points:
        by_candidate[point.candidate_id].append(point)
    outcome_by_id = {item.candidate_id: item for item in outcomes}
    if len(outcome_by_id) != len(outcomes):
        raise ValueError("duplicate candidate outcome")

    fidelity: list[PayoffFidelityItem] = []
    reasons: set[str] = set()
    for candidate_id in sorted(set(by_candidate) | set(outcome_by_id)):
        rows = by_candidate.get(candidate_id, [])
        item_reasons: set[str] = set()
        if len(rows) < policy.minimum_scenarios:
            quality = AttributionQuality.INSUFFICIENT_EVIDENCE
            item_reasons.add("P9_ATTRIBUTION_PAYOFF_SCENARIOS_INSUFFICIENT")
            mae = None
            rmse = None
        else:
            total_weight = sum(row.probability_weight for row in rows)
            errors = [row.candidate_payoff_per_unit - row.target_payoff_per_unit for row in rows]
            weighted_absolute_error = sum(
                abs(err) * row.probability_weight
                for err, row in zip(errors, rows, strict=True)
            )
            mae = weighted_absolute_error / total_weight
            rmse = (
                sum(err * err * row.probability_weight for err, row in zip(errors, rows))
                / total_weight
            ) ** 0.5
            if mae > policy.fidelity_tolerance:
                quality = AttributionQuality.LIMITED
                item_reasons.add("P9_ATTRIBUTION_PAYOFF_FIDELITY_LOW")
            else:
                quality = AttributionQuality.QUALIFIED
        fidelity.append(
            PayoffFidelityItem(
                candidate_id=candidate_id,
                scenario_count=len(rows),
                weighted_mae=mae,
                weighted_rmse=rmse,
                quality=quality,
                reason_codes=tuple(sorted(item_reasons)),
            )
        )
        reasons.update(item_reasons)

    estimates = tuple(
        _estimate_item(item) for item in sorted(outcomes, key=lambda row: row.candidate_id)
    )
    candidate_count = len(outcomes)
    observable = [
        item
        for item in outcomes
        if item.observable and item.realized_unit_pnl is not None
    ]
    coverage = len(observable) / candidate_count if candidate_count else 0.0
    selected = [item for item in outcomes if item.selected_by_p6]
    if len(selected) > 1:
        raise ValueError("P6 unit-shape evaluation expects at most one selected candidate")
    selected_item = selected[0] if selected else None
    best = max(observable, key=lambda item: item.realized_unit_pnl or float("-inf"), default=None)
    regret: float | None = None
    aggregate_effect: float | None = None
    if (
        selected_item is not None
        and selected_item.realized_unit_pnl is not None
        and best is not None
    ):
        regret = (best.realized_unit_pnl or 0.0) - selected_item.realized_unit_pnl
        aggregate_effect = -regret
    elif policy.require_observable_regret:
        reasons.add("P9_ATTRIBUTION_SYNTHESIS_REGRET_NOT_IDENTIFIABLE")

    if candidate_count == 0:
        quality = AttributionQuality.INSUFFICIENT_EVIDENCE
        reasons.add("P9_ATTRIBUTION_CANDIDATE_UNIVERSE_INCOMPLETE")
    elif regret is None and policy.require_observable_regret:
        quality = AttributionQuality.NOT_IDENTIFIABLE
    elif any(item.quality is AttributionQuality.INSUFFICIENT_EVIDENCE for item in fidelity):
        quality = AttributionQuality.INSUFFICIENT_EVIDENCE
    elif any(item.quality is AttributionQuality.LIMITED for item in fidelity):
        quality = AttributionQuality.LIMITED
    else:
        quality = AttributionQuality.QUALIFIED

    payload = {
        "fidelity": [item.model_dump(mode="json") for item in fidelity],
        "estimates": [item.model_dump(mode="json") for item in estimates],
        "coverage_ratio": coverage,
        "selected": selected_item.candidate_id if selected_item else None,
        "best": best.candidate_id if best else None,
        "regret": regret,
        "aggregate_pnl_effect": aggregate_effect,
        "quality": quality,
        "reason_codes": sorted(reasons),
    }
    return PayoffAttributionResult(
        fidelity=tuple(fidelity),
        estimates=estimates,
        candidate_count=candidate_count,
        observable_candidate_count=len(observable),
        coverage_ratio=coverage,
        selected_candidate_id=selected_item.candidate_id if selected_item else None,
        best_observable_candidate_id=best.candidate_id if best else None,
        synthesis_regret=regret,
        aggregate_pnl_effect=aggregate_effect,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )


def _estimate_item(item: CandidateOutcome) -> EstimateAccuracyItem:
    maximum_loss_valid: bool | None = None
    if item.maximum_loss_bound is not None and item.observed_loss is not None:
        maximum_loss_valid = item.observed_loss <= item.maximum_loss_bound
    return EstimateAccuracyItem(
        candidate_id=item.candidate_id,
        price_error=_difference(item.actual_price, item.estimated_price),
        cost_error=_difference(item.actual_cost, item.estimated_cost),
        liquidity_error=_difference(item.actual_liquidity, item.estimated_liquidity),
        risk_error=_difference(item.actual_risk, item.estimated_risk),
        maximum_loss_proof_valid=maximum_loss_valid,
        evidence_class=item.evidence_class,
    )


def _difference(actual: float | None, estimate: float | None) -> float | None:
    if actual is None or estimate is None:
        return None
    return actual - estimate
