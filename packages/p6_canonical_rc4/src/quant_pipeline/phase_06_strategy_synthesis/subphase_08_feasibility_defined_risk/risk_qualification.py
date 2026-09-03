"""Final scenario sanity, risk summary, and rejection construction."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.models import (
    CandidateQualification,
    CandidateRiskSummary,
    RejectionRecord,
    ScenarioEvaluation,
    StrategyCandidate,
    StrategyPayoffRecord,
)
from ..domain.statistics import expected_shortfall, weighted_mean, weighted_quantile
from ..foundation.hashing import stable_id
from .qualification_gates import _with_reasons

ZERO = Decimal("0")

def final_sanity_and_risk(
    qualifications: tuple[CandidateQualification, ...],
    candidates: tuple[StrategyCandidate, ...],
    payoffs: tuple[StrategyPayoffRecord, ...],
    scenarios: tuple[ScenarioEvaluation, ...],
) -> tuple[
    tuple[CandidateQualification, ...],
    tuple[CandidateRiskSummary, ...],
    tuple[RejectionRecord, ...],
]:
    candidate_by_id = {item.candidate_id: item for item in candidates}
    payoff_by_id = {item.candidate_id: item for item in payoffs}
    scenarios_by_id: dict[str, list[ScenarioEvaluation]] = defaultdict(list)
    for scenario in scenarios:
        scenarios_by_id[scenario.candidate_id].append(scenario)

    final: list[CandidateQualification] = []
    risks: list[CandidateRiskSummary] = []
    rejected: list[RejectionRecord] = []
    for item in qualifications:
        candidate = candidate_by_id[item.candidate_id]
        payoff = payoff_by_id[item.candidate_id]
        candidate_scenarios = scenarios_by_id[item.candidate_id]
        reasons = list(item.reason_codes)
        if not candidate_scenarios:
            reasons.append("P6_P5_SCENARIO_INVALID")
        if candidate_scenarios:
            risks.append(
                _risk_summary(
                    item,
                    payoff,
                    candidate_scenarios,
                )
            )
        final_item = _with_reasons(item, reasons)
        final.append(final_item)
        if not final_item.qualified:
            rejected.append(
                _rejection_record(
                    candidate,
                    final_item.reason_codes,
                )
            )
    return tuple(final), tuple(risks), tuple(rejected)


def _risk_summary(
    qualification: CandidateQualification,
    payoff: StrategyPayoffRecord,
    scenarios: list[ScenarioEvaluation],
) -> CandidateRiskSummary:
    values = [row.scenario_pnl for row in scenarios]
    probabilities = [row.scenario_probability for row in scenarios]
    expected = weighted_mean(values, probabilities)
    median = weighted_quantile(values, probabilities, Decimal("0.5"))
    lower = weighted_quantile(values, probabilities, Decimal("0.05"))
    upper = weighted_quantile(values, probabilities, Decimal("0.95"))
    probability_of_profit = sum(
        (
            probability
            for value, probability in zip(values, probabilities)
            if value > ZERO
        ),
        ZERO,
    )
    return CandidateRiskSummary(
        candidate_id=qualification.candidate_id,
        expected_net_payoff=expected,
        median_net_payoff=median,
        probability_of_profit=probability_of_profit,
        lower_quantile=lower,
        upper_quantile=upper,
        value_at_risk=max(ZERO, -lower),
        expected_shortfall=expected_shortfall(values, probabilities),
        maximum_loss=payoff.maximum_loss,
        maximum_gain=payoff.maximum_gain,
        return_on_max_loss=_safe_ratio(expected, payoff.maximum_loss),
        return_on_margin=_safe_ratio(expected, qualification.margin_estimate),
        break_even_points=payoff.break_even_points,
    )


def _safe_ratio(
    numerator: Decimal,
    denominator: Decimal | None,
) -> Decimal | None:
    if denominator in (None, ZERO):
        return None
    return numerator / denominator


def _rejection_record(
    candidate: StrategyCandidate,
    reasons: tuple[str, ...],
) -> RejectionRecord:
    return RejectionRecord(
        rejection_id=stable_id(
            "rejection",
            candidate.candidate_id,
            reasons,
        ),
        candidate_id=candidate.candidate_id,
        template_id=candidate.origin_template_id,
        stage="P6.S8",
        reason_code=reasons[0],
        details={"reason_codes": list(reasons)},
    )
