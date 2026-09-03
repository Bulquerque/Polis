"""Temporary P7 V1 projection from the canonical multi-leg strategy domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import sqrt

from ..domain.enums import InstrumentType
from ..domain.models import (
    CandidateQualification,
    CandidateRiskSummary,
    GreekState,
    LegacyCandidateFeatureRecord,
    LegacyCandidateUniverseRecord,
    LegacyGenerationLogRecord,
    LegacyOptionFeatureRecord,
    LegacyQualityRecord,
    MarketBeliefState,
    StrategyCandidate,
)
from ..foundation.artifacts import PIPELINE_VERSION

ZERO = Decimal("0")
ONE = Decimal("1")
LegacyProjection = tuple[
    tuple[LegacyCandidateFeatureRecord, ...],
    tuple[LegacyCandidateUniverseRecord, ...],
    tuple[LegacyOptionFeatureRecord, ...],
    tuple[LegacyQualityRecord, ...],
    tuple[LegacyGenerationLogRecord, ...],
]
ProjectedCandidate = tuple[
    LegacyCandidateFeatureRecord,
    LegacyCandidateUniverseRecord,
    LegacyOptionFeatureRecord,
    LegacyQualityRecord,
    LegacyGenerationLogRecord,
]


def project_legacy_records(
    candidates: tuple[StrategyCandidate, ...],
    risks: tuple[CandidateRiskSummary, ...],
    greeks: tuple[GreekState, ...],
    qualifications: tuple[CandidateQualification, ...],
    beliefs: tuple[MarketBeliefState, ...],
    available_at: datetime,
) -> LegacyProjection:
    """Project canonical strategies to the explicitly degraded P7 V1 surface."""
    risk_by_id = {item.candidate_id: item for item in risks}
    greek_by_id = {item.candidate_id: item for item in greeks}
    qualification_by_id = {item.candidate_id: item for item in qualifications}
    belief_by_underlying = {item.underlying_id: item for item in beliefs}
    projected = tuple(
        _project_candidate(
            candidate,
            risk_by_id[candidate.candidate_id],
            greek_by_id[candidate.candidate_id],
            qualification_by_id[candidate.candidate_id],
            belief_by_underlying[candidate.underlying_id],
            available_at,
        )
        for candidate in candidates
    )
    return (
        tuple(records[0] for records in projected),
        tuple(records[1] for records in projected),
        tuple(records[2] for records in projected),
        tuple(records[3] for records in projected),
        tuple(records[4] for records in projected),
    )


def _project_candidate(
    candidate: StrategyCandidate,
    risk: CandidateRiskSummary,
    greek: GreekState,
    qualification: CandidateQualification,
    belief: MarketBeliefState,
    available_at: datetime,
) -> ProjectedCandidate:
    maximum_loss = risk.maximum_loss if risk.maximum_loss is not None else ZERO
    capital = max(maximum_loss, abs(risk.expected_net_payoff), ONE)
    daily = _normalize_horizon(risk.expected_net_payoff / capital, candidate.horizon_days)
    volatility = _scenario_volatility(belief, capital)
    feature = _feature_record(
        candidate,
        risk,
        belief,
        available_at,
        capital,
        daily,
        (ONE + daily) ** 5 - ONE,
        (ONE + daily) ** 21 - ONE,
        volatility,
    )
    universe = LegacyCandidateUniverseRecord(
        candidate_id=candidate.candidate_id,
        underlying=candidate.underlying_id,
        action_type=candidate.origin_template_id.value,
        leg_count=len(candidate.legs),
    )
    option = LegacyOptionFeatureRecord(
        candidate_id=candidate.candidate_id,
        option_leg_count=sum(
            1
            for leg in candidate.legs
            if leg.instrument_type is InstrumentType.OPTION
        ),
        delta=greek.delta,
        gamma=greek.gamma,
        vega=greek.vega,
        theta=greek.theta,
    )
    quality = LegacyQualityRecord(
        candidate_id=candidate.candidate_id,
        contract_exists=True,
        quality_status=greek.status.value,
        reason_codes=qualification.reason_codes,
    )
    log = LegacyGenerationLogRecord(
        candidate_id=candidate.candidate_id,
        origin_template=candidate.origin_template_id.value,
        generation_run_id=candidate.generation_run_id,
        qualification_status="QUALIFIED" if qualification.qualified else "REJECTED",
    )
    return feature, universe, option, quality, log


def _feature_record(
    candidate: StrategyCandidate,
    risk: CandidateRiskSummary,
    belief: MarketBeliefState,
    available_at: datetime,
    capital: Decimal,
    daily: Decimal,
    weekly: Decimal,
    monthly: Decimal,
    volatility: Decimal,
) -> LegacyCandidateFeatureRecord:
    risk_score = risk.maximum_loss / capital if risk.maximum_loss is not None else ONE
    return LegacyCandidateFeatureRecord(
        date=candidate.decision_time.date().isoformat(),
        as_of_date=candidate.decision_time.date().isoformat(),
        available_at=available_at,
        candidate_id=candidate.candidate_id,
        underlying=candidate.underlying_id,
        action_type=candidate.origin_template_id.value,
        capital_reference=capital,
        reference_price_t=capital,
        source_id="P6_STRATEGY_V2_PROJECTION",
        lineage_id=candidate.lineage_id,
        pipeline_version=PIPELINE_VERSION,
        expected_return_d=daily,
        expected_return_w=weekly,
        expected_return_m=monthly,
        volatility_forecast=volatility,
        risk_score=risk_score,
        tail_risk_score=risk.expected_shortfall / capital,
        forecast_confidence=belief.confidence,
        regime_context=belief.regime_context,
        data_quality_score=belief.confidence_components.get("data_quality"),
        ood_score=(
            None
            if belief.confidence_components.get("ood") is None
            else ONE - belief.confidence_components["ood"]
        ),
    )


def _normalize_horizon(total_return: Decimal, horizon_days: int) -> Decimal:
    if total_return <= -ONE:
        return -ONE
    normalized = (1 + float(total_return)) ** (1 / max(horizon_days, 1)) - 1
    return Decimal(str(normalized))


def _scenario_volatility(
    belief: MarketBeliefState,
    capital: Decimal,
) -> Decimal:
    prices = [scenario.terminal_underlying_price for scenario in belief.scenarios]
    probabilities = [scenario.probability for scenario in belief.scenarios]
    mean = sum(
        (value * probability for value, probability in zip(prices, probabilities)),
        ZERO,
    )
    variance = sum(
        (
            (value - mean) * (value - mean) * probability
            for value, probability in zip(prices, probabilities)
        ),
        ZERO,
    )
    return Decimal(str(sqrt(float(variance)))) / capital
