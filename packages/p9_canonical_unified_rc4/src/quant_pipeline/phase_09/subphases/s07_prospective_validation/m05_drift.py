"""P9.S7.M05 — multichannel drift and changepoint ensemble."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from math import pi, sqrt
from statistics import fmean, pvariance

import numpy as np
from scipy.special import logsumexp
from pydantic import Field, field_validator, model_validator

from .canonical import payload_sha256
from .contracts import NonEmptyStr, StrictModel
from .errors import NumericalDomainError


class DriftChannelKind(StrEnum):
    INPUT = "INPUT"
    MISSINGNESS = "MISSINGNESS"
    FORECAST_RESIDUAL = "FORECAST_RESIDUAL"
    CALIBRATION = "CALIBRATION"
    PNL = "PNL"
    COST = "COST"
    LIQUIDITY = "LIQUIDITY"
    FACTOR_EXPOSURE = "FACTOR_EXPOSURE"
    POLICY_ACTION = "POLICY_ACTION"


class DriftObservation(StrictModel):
    channel_id: NonEmptyStr
    channel_kind: DriftChannelKind
    observed_at: datetime
    value: float | None

    @field_validator("observed_at")
    @classmethod
    def observed_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("observed_at must be UTC")
        return value


class DriftChannelPolicy(StrictModel):
    channel_id: NonEmptyStr
    channel_kind: DriftChannelKind
    reference_window: int = Field(default=50, ge=10)
    test_window: int = Field(default=20, ge=5)
    mean_shift_z_threshold: float = Field(default=3.0, gt=0.0)
    variance_ratio_threshold: float = Field(default=2.0, gt=1.0)
    cusum_threshold: float = Field(default=5.0, gt=0.0)
    cusum_allowance: float = Field(default=0.5, ge=0.0)
    bocpd_hazard: float = Field(default=0.02, gt=0.0, lt=1.0)
    bocpd_alert_probability: float = Field(default=0.5, gt=0.0, lt=1.0)
    bocpd_max_run_length: int = Field(default=256, ge=20)
    missingness_delta_threshold: float = Field(default=0.2, gt=0.0, le=1.0)
    hard_breach: bool = False

    @model_validator(mode="after")
    def validate_windows(self) -> "DriftChannelPolicy":
        if self.reference_window <= self.test_window:
            raise ValueError("reference_window must exceed test_window")
        return self


class DetectorEvidence(StrictModel):
    detector_name: NonEmptyStr
    statistic: float | None
    threshold: float | None
    alerted: bool
    details: tuple[tuple[NonEmptyStr, float], ...] = ()


class ChannelDriftEvent(StrictModel):
    channel_id: NonEmptyStr
    channel_kind: DriftChannelKind
    observation_count: int = Field(ge=0)
    estimated_change_time: datetime | None
    severity: float = Field(ge=0.0)
    alerted: bool
    hard_breach: bool
    detector_evidence: tuple[DetectorEvidence, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class CrossChannelAgreement(StrictModel):
    alerted_channel_ids: tuple[NonEmptyStr, ...]
    confirmed: bool
    hard_breach_present: bool
    agreement_ratio: float = Field(ge=0.0, le=1.0)
    reason_codes: tuple[NonEmptyStr, ...] = ()


class DriftQualificationResult(StrictModel):
    channel_events: tuple[ChannelDriftEvent, ...]
    agreement: CrossChannelAgreement
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def detect_multichannel_drift(
    observations: tuple[DriftObservation, ...],
    policies: tuple[DriftChannelPolicy, ...],
    minimum_confirming_channels: int = 2,
) -> DriftQualificationResult:
    """Run transparent detector evidence per channel and aggregate conservatively."""

    if minimum_confirming_channels < 1:
        raise ValueError("minimum_confirming_channels must be positive")
    policy_by_id = {policy.channel_id: policy for policy in policies}
    if len(policy_by_id) != len(policies):
        raise ValueError("duplicate drift policy")
    grouped: dict[str, list[DriftObservation]] = defaultdict(list)
    for observation in sorted(observations, key=lambda item: (item.channel_id, item.observed_at)):
        grouped[observation.channel_id].append(observation)
    unknown = set(grouped) - set(policy_by_id)
    if unknown:
        raise ValueError(f"P9_LIVE_DRIFT_POLICY_UNREGISTERED: {sorted(unknown)}")

    events = tuple(
        _detect_channel(tuple(grouped.get(policy.channel_id, ())), policy)
        for policy in sorted(policies, key=lambda item: item.channel_id)
    )
    alerted = tuple(event.channel_id for event in events if event.alerted)
    hard = any(event.alerted and event.hard_breach for event in events)
    confirmed = hard or len(alerted) >= minimum_confirming_channels
    ratio = len(alerted) / len(events) if events else 0.0
    reason_codes: list[str] = []
    if alerted and not confirmed:
        reason_codes.append("P9_LIVE_DRIFT_SINGLE_CHANNEL_UNCONFIRMED")
    if any("P9_LIVE_DATA_QUALITY_DEGRADATION" in event.reason_codes for event in events):
        reason_codes.append("P9_LIVE_DATA_QUALITY_DEGRADATION")
    agreement = CrossChannelAgreement(
        alerted_channel_ids=alerted,
        confirmed=confirmed,
        hard_breach_present=hard,
        agreement_ratio=ratio,
        reason_codes=tuple(sorted(set(reason_codes))),
    )
    payload = {
        "events": [event.model_dump(mode="json") for event in events],
        "agreement": agreement.model_dump(mode="json"),
    }
    return DriftQualificationResult(
        channel_events=events,
        agreement=agreement,
        result_sha256=payload_sha256(payload),
    )


def _detect_channel(
    observations: tuple[DriftObservation, ...],
    policy: DriftChannelPolicy,
) -> ChannelDriftEvent:
    missing = [item.value is None for item in observations]
    numeric = [float(item.value) for item in observations if item.value is not None]
    evidence: list[DetectorEvidence] = []
    reasons: list[str] = []
    estimated_time: datetime | None = None

    required = policy.reference_window + policy.test_window
    if len(observations) < required:
        return ChannelDriftEvent(
            channel_id=policy.channel_id,
            channel_kind=policy.channel_kind,
            observation_count=len(observations),
            estimated_change_time=None,
            severity=0.0,
            alerted=False,
            hard_breach=policy.hard_breach,
            detector_evidence=(),
            reason_codes=("P9_LIVE_DRIFT_SAMPLE_INSUFFICIENT",),
        )

    reference_obs = observations[-required : -policy.test_window]
    test_obs = observations[-policy.test_window :]
    reference_missing = fmean(1.0 if item.value is None else 0.0 for item in reference_obs)
    test_missing = fmean(1.0 if item.value is None else 0.0 for item in test_obs)
    missing_delta = test_missing - reference_missing
    missing_alert = missing_delta >= policy.missingness_delta_threshold
    evidence.append(
        DetectorEvidence(
            detector_name="MISSINGNESS_DELTA",
            statistic=missing_delta,
            threshold=policy.missingness_delta_threshold,
            alerted=missing_alert,
        )
    )
    if missing_alert:
        reasons.append("P9_LIVE_DATA_QUALITY_DEGRADATION")

    reference = [float(item.value) for item in reference_obs if item.value is not None]
    test = [float(item.value) for item in test_obs if item.value is not None]
    if len(reference) >= 5 and len(test) >= 3:
        mean_ref = fmean(reference)
        mean_test = fmean(test)
        var_ref = pvariance(reference) if len(reference) > 1 else 0.0
        var_test = pvariance(test) if len(test) > 1 else 0.0
        pooled_se = sqrt(max(var_ref / len(reference) + var_test / len(test), 1e-18))
        mean_z = abs(mean_test - mean_ref) / pooled_se
        mean_alert = mean_z >= policy.mean_shift_z_threshold
        variance_ratio = max(var_test, 1e-18) / max(var_ref, 1e-18)
        variance_alert = (
            variance_ratio >= policy.variance_ratio_threshold
            or variance_ratio <= 1.0 / policy.variance_ratio_threshold
        )
        evidence.extend(
            [
                DetectorEvidence(
                    detector_name="WINDOW_MEAN_SHIFT",
                    statistic=mean_z,
                    threshold=policy.mean_shift_z_threshold,
                    alerted=mean_alert,
                ),
                DetectorEvidence(
                    detector_name="WINDOW_VARIANCE_RATIO",
                    statistic=variance_ratio,
                    threshold=policy.variance_ratio_threshold,
                    alerted=variance_alert,
                ),
            ]
        )
        cusum_stat, cusum_index = _cusum(reference, test, policy)
        cusum_alert = cusum_stat >= policy.cusum_threshold
        evidence.append(
            DetectorEvidence(
                detector_name="STANDARDIZED_CUSUM",
                statistic=cusum_stat,
                threshold=policy.cusum_threshold,
                alerted=cusum_alert,
            )
        )
        if cusum_alert:
            estimated_time = test_obs[cusum_index].observed_at

        cp_probabilities = _bocpd_gaussian(
            numeric,
            hazard=policy.bocpd_hazard,
            max_run_length=policy.bocpd_max_run_length,
        )
        cp_probability = cp_probabilities[-1] if cp_probabilities else 0.0
        bocpd_alert = cp_probability >= policy.bocpd_alert_probability
        evidence.append(
            DetectorEvidence(
                detector_name="GAUSSIAN_BOCPD_SHORT_RUN_MASS",
                statistic=cp_probability,
                threshold=policy.bocpd_alert_probability,
                alerted=bocpd_alert,
            )
        )
        if bocpd_alert and estimated_time is None:
            estimated_time = observations[-1].observed_at

    alerted_evidence = [item for item in evidence if item.alerted]
    severity = min(1.0, len(alerted_evidence) / max(1, len(evidence)))
    return ChannelDriftEvent(
        channel_id=policy.channel_id,
        channel_kind=policy.channel_kind,
        observation_count=len(observations),
        estimated_change_time=estimated_time,
        severity=severity,
        alerted=bool(alerted_evidence),
        hard_breach=policy.hard_breach,
        detector_evidence=tuple(evidence),
        reason_codes=tuple(sorted(set(reasons))),
    )


def _cusum(
    reference: list[float],
    test: list[float],
    policy: DriftChannelPolicy,
) -> tuple[float, int]:
    mean_ref = fmean(reference)
    std_ref = sqrt(max(pvariance(reference), 1e-18))
    positive = 0.0
    negative = 0.0
    best = 0.0
    best_index = 0
    for index, value in enumerate(test):
        standardized = (value - mean_ref) / std_ref
        positive = max(0.0, positive + standardized - policy.cusum_allowance)
        negative = min(0.0, negative + standardized + policy.cusum_allowance)
        statistic = max(positive, abs(negative))
        if statistic > best:
            best = statistic
            best_index = index
    return best, best_index


def _normal_logpdf(value: float, mean: np.ndarray, variance: np.ndarray) -> np.ndarray:
    return -0.5 * (np.log(2.0 * pi * variance) + (value - mean) ** 2 / variance)


def _bocpd_gaussian(
    values: list[float],
    hazard: float,
    max_run_length: int,
) -> list[float]:
    """Return posterior mass on short run lengths using Gaussian BOCPD.

    The calculation is performed in log space to avoid underflow during abrupt
    shifts. With a constant hazard, the exact run-length-zero probability is
    close to the hazard; short-run posterior mass is therefore the useful
    detection statistic.
    """

    if not values:
        return []
    initial = np.asarray(values[: min(len(values), 20)], dtype=np.float64)
    full = np.asarray(values, dtype=np.float64)
    variance = max(float(np.var(initial)), float(np.var(full)) * 1e-4, 1e-6)
    observation_variance = variance
    prior_mean = float(values[0])
    prior_variance = observation_variance * 10.0
    log_run_prob = np.array([0.0], dtype=np.float64)
    posterior_mean = np.array([prior_mean], dtype=np.float64)
    posterior_variance = np.array([prior_variance], dtype=np.float64)
    short_run_probabilities: list[float] = []

    for value in values:
        predictive_variance = observation_variance + posterior_variance
        log_predictive = _normal_logpdf(value, posterior_mean, predictive_variance)
        log_change = logsumexp(log_run_prob + np.log(hazard) + log_predictive)
        log_growth = log_run_prob + np.log1p(-hazard) + log_predictive
        new_log_prob = np.concatenate(([log_change], log_growth))[: max_run_length + 1]
        normalizer = float(logsumexp(new_log_prob))
        if not np.isfinite(normalizer):
            raise NumericalDomainError("BOCPD posterior normalization failed")
        new_log_prob -= normalizer
        short_run_cutoff = min(3, len(new_log_prob))
        short_run_probabilities.append(float(np.exp(logsumexp(new_log_prob[:short_run_cutoff]))))

        prior_precision = 1.0 / prior_variance
        observation_precision = 1.0 / observation_variance
        reset_variance = 1.0 / (prior_precision + observation_precision)
        reset_mean = reset_variance * (
            prior_precision * prior_mean + observation_precision * value
        )
        growth_precision = 1.0 / posterior_variance + observation_precision
        growth_variance = 1.0 / growth_precision
        growth_mean = growth_variance * (
            posterior_mean / posterior_variance + observation_precision * value
        )
        posterior_mean = np.concatenate(([reset_mean], growth_mean))[: max_run_length + 1]
        posterior_variance = np.concatenate(([reset_variance], growth_variance))[
            : max_run_length + 1
        ]
        log_run_prob = new_log_prob
    return short_run_probabilities
