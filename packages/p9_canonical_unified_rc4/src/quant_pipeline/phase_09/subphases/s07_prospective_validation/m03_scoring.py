"""P9.S7.M03 — online proper scoring, calibration, and reliability."""

from __future__ import annotations

from .errors import InvariantViolation

from collections import defaultdict
from math import erf, exp, log, pi, sqrt
from statistics import fmean

from pydantic import Field, model_validator

from .canonical import payload_sha256
from .contracts import MaturityState, NonEmptyStr, StrictModel
from .m01_prequential import (
    BinaryProbabilityForecast,
    DecisionKind,
    IntervalForecast,
    NormalForecast,
    PointForecast,
    PrequentialRecord,
    QuantileForecast,
)


class ScoringPolicy(StrictModel):
    probability_floor: float = Field(default=1e-12, gt=0.0, lt=0.5)
    minimum_calibration_count: int = Field(default=10, ge=2)
    binary_bin_edges: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)

    @model_validator(mode="after")
    def validate_bins(self) -> "ScoringPolicy":
        if self.binary_bin_edges[0] != 0.0 or self.binary_bin_edges[-1] != 1.0:
            raise ValueError("binary bins must start at 0 and end at 1")
        if tuple(sorted(set(self.binary_bin_edges))) != self.binary_bin_edges:
            raise ValueError("binary bin edges must be unique and increasing")
        return self


class OnlineScoreRecord(StrictModel):
    prediction_event_id: NonEmptyStr
    cohort_id: NonEmptyStr
    policy_id: NonEmptyStr
    target_id: NonEmptyStr
    horizon_id: NonEmptyStr
    score_name: NonEmptyStr
    score_value: float | None
    quality_state: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()


class CalibrationBin(StrictModel):
    policy_id: NonEmptyStr
    lower_edge: float
    upper_edge: float
    observation_count: int = Field(ge=0)
    mean_prediction: float | None = None
    observed_frequency: float | None = None
    qualified: bool


class ReliabilitySummary(StrictModel):
    policy_id: NonEmptyStr
    target_id: NonEmptyStr
    horizon_id: NonEmptyStr
    observation_count: int = Field(ge=0)
    mean_score_by_name: tuple[tuple[NonEmptyStr, float], ...]
    empirical_coverage: float | None = None
    mean_interval_width: float | None = None
    abstention_rate: float
    calibration_qualified: bool


class OnlineScoringResult(StrictModel):
    score_records: tuple[OnlineScoreRecord, ...]
    calibration_bins: tuple[CalibrationBin, ...]
    summaries: tuple[ReliabilitySummary, ...]
    score_panel_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[NonEmptyStr, ...] = ()


def score_prequential_records(
    records: tuple[PrequentialRecord, ...],
    policy: ScoringPolicy,
) -> OnlineScoringResult:
    """Score each matured record exactly once and aggregate by policy/target/horizon."""

    scores: list[OnlineScoreRecord] = []
    reason_codes: set[str] = set()
    binary_observations: dict[str, list[tuple[float, float]]] = defaultdict(list)
    interval_observations: dict[tuple[str, str, str], list[tuple[bool, float]]] = defaultdict(list)
    group_score_values: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    group_counts: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total": 0, "abstain": 0}
    )

    for record in records:
        key = (
            record.prediction.policy_id,
            record.prediction.target_id,
            record.prediction.horizon_id,
        )
        group_counts[key]["total"] += 1
        if record.prediction.decision_kind is DecisionKind.ABSTAIN:
            group_counts[key]["abstain"] += 1
        outcome = record.active_outcome
        if outcome is None or outcome.maturity_state not in {
            MaturityState.MATURED,
            MaturityState.SETTLED,
        }:
            reason_codes.add("P9_MATURITY_NOT_REACHED")
            continue
        if outcome.value is None:
            raise InvariantViolation("matured outcome lacks a realized value")
        event_scores = _score_forecast(record, outcome.value, policy)
        scores.extend(event_scores)
        for score in event_scores:
            if score.score_value is not None:
                group_score_values[key][score.score_name].append(score.score_value)
        forecast = record.prediction.forecast
        if isinstance(forecast, BinaryProbabilityForecast) and outcome.value in {0.0, 1.0}:
            binary_observations[record.prediction.policy_id].append(
                (forecast.probability, outcome.value)
            )
        if isinstance(forecast, IntervalForecast):
            covered = forecast.lower <= outcome.value <= forecast.upper
            interval_observations[key].append((covered, forecast.upper - forecast.lower))

    calibration_bins = _build_calibration_bins(binary_observations, policy)
    summaries: list[ReliabilitySummary] = []
    for key in sorted(group_counts):
        policy_id, target_id, horizon_id = key
        counts = group_counts[key]
        interval_values = interval_observations.get(key, [])
        score_means = tuple(
            sorted(
                (name, fmean(values))
                for name, values in group_score_values.get(key, {}).items()
                if values
            )
        )
        summaries.append(
            ReliabilitySummary(
                policy_id=policy_id,
                target_id=target_id,
                horizon_id=horizon_id,
                observation_count=sum(
                    len(values)
                    for values in group_score_values.get(key, {}).values()
                ),
                mean_score_by_name=score_means,
                empirical_coverage=(
                    fmean(1.0 if covered else 0.0 for covered, _ in interval_values)
                    if interval_values
                    else None
                ),
                mean_interval_width=(
                    fmean(width for _, width in interval_values)
                    if interval_values
                    else None
                ),
                abstention_rate=counts["abstain"] / counts["total"] if counts["total"] else 0.0,
                calibration_qualified=any(
                    item.policy_id == policy_id and item.qualified for item in calibration_bins
                ),
            )
        )

    payload = [score.model_dump(mode="json") for score in scores]
    return OnlineScoringResult(
        score_records=tuple(scores),
        calibration_bins=tuple(calibration_bins),
        summaries=tuple(summaries),
        score_panel_sha256=payload_sha256(payload),
        reason_codes=tuple(sorted(reason_codes)),
    )


def _score_forecast(
    record: PrequentialRecord,
    outcome: float,
    policy: ScoringPolicy,
) -> list[OnlineScoreRecord]:
    forecast = record.prediction.forecast
    base = {
        "prediction_event_id": record.prediction.event_id,
        "cohort_id": record.prediction.cohort_id,
        "policy_id": record.prediction.policy_id,
        "target_id": record.prediction.target_id,
        "horizon_id": record.prediction.horizon_id,
    }
    if isinstance(forecast, BinaryProbabilityForecast):
        if outcome not in {0.0, 1.0}:
            return [_invalid_score(base, "BINARY_SCORE", "P9_LIVE_SCORING_POLICY_MISMATCH")]
        probability = forecast.probability
        brier = (probability - outcome) ** 2
        if (probability == 0.0 and outcome == 1.0) or (probability == 1.0 and outcome == 0.0):
            log_record = _invalid_score(
                base,
                "LOG_LOSS",
                "P9_LIVE_ZERO_PROBABILITY_CONTRADICTION",
            )
        else:
            p = min(max(probability, policy.probability_floor), 1.0 - policy.probability_floor)
            log_loss = -(outcome * log(p) + (1.0 - outcome) * log(1.0 - p))
            log_record = OnlineScoreRecord(
                **base,
                score_name="LOG_LOSS",
                score_value=log_loss,
                quality_state="QUALIFIED",
            )
        return [
            OnlineScoreRecord(
                **base,
                score_name="BRIER",
                score_value=brier,
                quality_state="QUALIFIED",
            ),
            log_record,
        ]
    if isinstance(forecast, NormalForecast):
        z = (outcome - forecast.mean) / forecast.standard_deviation
        nll = log(forecast.standard_deviation * sqrt(2.0 * pi)) + 0.5 * z * z
        phi = exp(-0.5 * z * z) / sqrt(2.0 * pi)
        cdf = 0.5 * (1.0 + erf(z / sqrt(2.0)))
        crps = forecast.standard_deviation * (
            z * (2.0 * cdf - 1.0) + 2.0 * phi - 1.0 / sqrt(pi)
        )
        return [
            OnlineScoreRecord(
                **base,
                score_name="NORMAL_NLL",
                score_value=nll,
                quality_state="QUALIFIED",
            ),
            OnlineScoreRecord(
                **base,
                score_name="NORMAL_CRPS",
                score_value=crps,
                quality_state="QUALIFIED",
            ),
        ]
    if isinstance(forecast, QuantileForecast):
        values = []
        for point in forecast.points:
            error = outcome - point.value
            values.append((point.quantile - (1.0 if error < 0.0 else 0.0)) * error)
        return [
            OnlineScoreRecord(
                **base,
                score_name="MEAN_PINBALL",
                score_value=fmean(values),
                quality_state="QUALIFIED",
            )
        ]
    if isinstance(forecast, IntervalForecast):
        alpha = 1.0 - forecast.nominal_coverage
        score = forecast.upper - forecast.lower
        if outcome < forecast.lower:
            score += 2.0 / alpha * (forecast.lower - outcome)
        elif outcome > forecast.upper:
            score += 2.0 / alpha * (outcome - forecast.upper)
        return [
            OnlineScoreRecord(
                **base,
                score_name="INTERVAL_SCORE",
                score_value=score,
                quality_state="QUALIFIED",
            )
        ]
    if isinstance(forecast, PointForecast):
        return [
            OnlineScoreRecord(
                **base,
                score_name="ABSOLUTE_ERROR",
                score_value=abs(forecast.value - outcome),
                quality_state="LIMITED_POINT_FORECAST",
                reason_codes=("P9_LIVE_POINT_FORECAST_NOT_PROBABILISTIC",),
            )
        ]
    raise AssertionError("unreachable forecast type")


def _invalid_score(base: dict[str, str], name: str, reason: str) -> OnlineScoreRecord:
    return OnlineScoreRecord(
        **base,
        score_name=name,
        score_value=None,
        quality_state="INVALID",
        reason_codes=(reason,),
    )


def _build_calibration_bins(
    observations: dict[str, list[tuple[float, float]]],
    policy: ScoringPolicy,
) -> list[CalibrationBin]:
    result: list[CalibrationBin] = []
    for policy_id, values in sorted(observations.items()):
        for lower, upper in zip(policy.binary_bin_edges, policy.binary_bin_edges[1:]):
            selected = [
                (prediction, outcome)
                for prediction, outcome in values
                if lower <= prediction <= upper and (prediction < upper or upper == 1.0)
            ]
            qualified = len(selected) >= policy.minimum_calibration_count
            result.append(
                CalibrationBin(
                    policy_id=policy_id,
                    lower_edge=lower,
                    upper_edge=upper,
                    observation_count=len(selected),
                    mean_prediction=fmean(item[0] for item in selected) if selected else None,
                    observed_frequency=fmean(item[1] for item in selected) if selected else None,
                    qualified=qualified,
                )
            )
    return result
