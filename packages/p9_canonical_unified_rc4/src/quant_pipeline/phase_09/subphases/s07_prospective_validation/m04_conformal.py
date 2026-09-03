"""P9.S7.M04 — adaptive conformal coverage monitoring.

This is a deliberately bounded specialist implementation of Adaptive Conformal
Inference (ACI). It adjusts a miscoverage controller after matured outcomes and
reports coverage and sharpness together. It does not rewrite upstream forecasts.
"""

from __future__ import annotations

from collections import defaultdict, deque
from statistics import fmean

import numpy as np
from pydantic import Field, model_validator

from .canonical import payload_sha256
from .contracts import Availability, NonEmptyStr, StrictModel


class ConformalPolicy(StrictModel):
    availability: Availability = Availability.AVAILABLE
    target_coverage: float = Field(gt=0.0, lt=1.0)
    learning_rate: float = Field(gt=0.0, le=1.0)
    minimum_miscoverage: float = Field(default=0.001, gt=0.0, lt=0.5)
    maximum_miscoverage: float = Field(default=0.5, gt=0.0, lt=1.0)
    calibration_window: int = Field(default=200, ge=10)
    minimum_group_count: int = Field(default=20, ge=2)
    maximum_qualified_width: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ConformalPolicy":
        if self.minimum_miscoverage >= self.maximum_miscoverage:
            raise ValueError("minimum_miscoverage must be below maximum_miscoverage")
        return self


class ConformalObservation(StrictModel):
    event_id: NonEmptyStr
    group_id: NonEmptyStr
    lower: float
    upper: float
    outcome: float

    @model_validator(mode="after")
    def validate_interval(self) -> "ConformalObservation":
        if self.lower > self.upper:
            raise ValueError("lower must not exceed upper")
        return self


class ConformalStep(StrictModel):
    event_id: NonEmptyStr
    group_id: NonEmptyStr
    alpha_before: float
    error_indicator: int = Field(ge=0, le=1)
    alpha_after: float
    nonconformity_score: float = Field(ge=0.0)
    calibration_quantile: float | None
    interval_width: float = Field(ge=0.0)


class ConformalGroupSummary(StrictModel):
    group_id: NonEmptyStr
    observation_count: int = Field(ge=0)
    empirical_coverage: float | None
    target_coverage: float
    coverage_regret: float | None
    mean_interval_width: float | None
    recommended_miscoverage: float
    quality_state: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ConformalMonitoringResult(StrictModel):
    availability: Availability
    steps: tuple[ConformalStep, ...]
    summaries: tuple[ConformalGroupSummary, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: tuple[NonEmptyStr, ...] = ()


def monitor_adaptive_conformal(
    observations: tuple[ConformalObservation, ...],
    policy: ConformalPolicy,
) -> ConformalMonitoringResult:
    """Run bounded ACI updates by group using only previously observed scores."""

    if policy.availability is Availability.UNAVAILABLE:
        payload = {"availability": policy.availability, "steps": [], "summaries": []}
        return ConformalMonitoringResult(
            availability=Availability.UNAVAILABLE,
            steps=(),
            summaries=(),
            result_sha256=payload_sha256(payload),
            limitations=("P9_LIVE_CONFORMAL_CAPABILITY_UNAVAILABLE",),
        )

    target_miscoverage = 1.0 - policy.target_coverage
    alpha_by_group: dict[str, float] = defaultdict(lambda: target_miscoverage)
    score_history: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=policy.calibration_window)
    )
    errors: dict[str, list[int]] = defaultdict(list)
    widths: dict[str, list[float]] = defaultdict(list)
    steps: list[ConformalStep] = []

    for observation in observations:
        alpha_before = alpha_by_group[observation.group_id]
        history = score_history[observation.group_id]
        calibration_quantile = (
            _higher_quantile(tuple(history), 1.0 - alpha_before)
            if history
            else None
        )
        miss = int(not (observation.lower <= observation.outcome <= observation.upper))
        nonconformity = max(
            observation.lower - observation.outcome,
            observation.outcome - observation.upper,
            0.0,
        )
        alpha_after = float(
            np.clip(
                alpha_before + policy.learning_rate * (target_miscoverage - miss),
                policy.minimum_miscoverage,
                policy.maximum_miscoverage,
            )
        )
        step = ConformalStep(
            event_id=observation.event_id,
            group_id=observation.group_id,
            alpha_before=alpha_before,
            error_indicator=miss,
            alpha_after=alpha_after,
            nonconformity_score=nonconformity,
            calibration_quantile=calibration_quantile,
            interval_width=observation.upper - observation.lower,
        )
        steps.append(step)
        alpha_by_group[observation.group_id] = alpha_after
        history.append(nonconformity)
        errors[observation.group_id].append(miss)
        widths[observation.group_id].append(observation.upper - observation.lower)

    summaries: list[ConformalGroupSummary] = []
    for group_id in sorted(set(errors) | set(alpha_by_group)):
        group_errors = errors[group_id]
        group_widths = widths[group_id]
        count = len(group_errors)
        coverage = 1.0 - fmean(group_errors) if group_errors else None
        mean_width = fmean(group_widths) if group_widths else None
        reason_codes: list[str] = []
        quality = "QUALIFIED"
        if count < policy.minimum_group_count:
            quality = "INSUFFICIENT_EVIDENCE"
            reason_codes.append("P9_LIVE_CONFORMAL_GROUP_INSUFFICIENT")
        if policy.maximum_qualified_width is not None and mean_width is not None:
            if mean_width > policy.maximum_qualified_width:
                quality = "LIMITED"
                reason_codes.append("P9_LIVE_CONFORMAL_INTERVAL_UNUSABLE")
        if coverage is not None and coverage < policy.target_coverage - 0.1:
            quality = "LIMITED"
            reason_codes.append("P9_LIVE_CONFORMAL_COVERAGE_COLLAPSE")
        summaries.append(
            ConformalGroupSummary(
                group_id=group_id,
                observation_count=count,
                empirical_coverage=coverage,
                target_coverage=policy.target_coverage,
                coverage_regret=(
                    policy.target_coverage - coverage
                    if coverage is not None
                    else None
                ),
                mean_interval_width=mean_width,
                recommended_miscoverage=alpha_by_group[group_id],
                quality_state=quality,
                reason_codes=tuple(reason_codes),
            )
        )

    payload = {
        "availability": policy.availability,
        "steps": [step.model_dump(mode="json") for step in steps],
        "summaries": [summary.model_dump(mode="json") for summary in summaries],
    }
    limitations = (
        ("ACI_LONG_RUN_COVERAGE_ONLY",)
        if policy.availability is Availability.LIMITED
        else ()
    )
    return ConformalMonitoringResult(
        availability=policy.availability,
        steps=tuple(steps),
        summaries=tuple(summaries),
        result_sha256=payload_sha256(payload),
        limitations=limitations,
    )


def _higher_quantile(values: tuple[float, ...], probability: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.quantile(array, probability, method="higher"))
