"""P9.S7.M06 — conservative anytime-valid paired policy comparison."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from math import log, sqrt
from statistics import fmean

from pydantic import Field, model_validator

from .canonical import payload_sha256
from .contracts import NonEmptyStr, StrictModel


class ComparisonState(StrEnum):
    CHAMPION_SUPERIOR = "CHAMPION_SUPERIOR"
    CHALLENGER_SUPERIOR = "CHALLENGER_SUPERIOR"
    STATISTICALLY_INDISTINGUISHABLE = "STATISTICALLY_INDISTINGUISHABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    COMPARISON_INVALID = "COMPARISON_INVALID"


class PairedLossObservation(StrictModel):
    cohort_id: NonEmptyStr
    prediction_event_id: NonEmptyStr
    champion_policy_id: NonEmptyStr
    challenger_policy_id: NonEmptyStr
    champion_loss: float
    challenger_loss: float

    @model_validator(mode="after")
    def validate_policies(self) -> "PairedLossObservation":
        if self.champion_policy_id == self.challenger_policy_id:
            raise ValueError("champion and challenger must differ")
        return self


class SequentialComparisonPolicy(StrictModel):
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    minimum_samples: int = Field(default=30, ge=2)
    minimum_effect: float = Field(default=0.0, ge=0.0)
    loss_lower_bound: float
    loss_upper_bound: float
    maximum_family_size: int = Field(default=20, ge=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "SequentialComparisonPolicy":
        if self.loss_lower_bound >= self.loss_upper_bound:
            raise ValueError("loss_lower_bound must be below loss_upper_bound")
        return self


class TimeUniformPoint(StrictModel):
    sample_count: int = Field(ge=1)
    mean_loss_difference: float
    lower_bound: float
    upper_bound: float


class PolicyComparison(StrictModel):
    champion_policy_id: NonEmptyStr
    challenger_policy_id: NonEmptyStr
    state: ComparisonState
    sample_count: int = Field(ge=0)
    mean_loss_difference: float | None
    lower_bound: float | None
    upper_bound: float | None
    path: tuple[TimeUniformPoint, ...]
    reason_codes: tuple[NonEmptyStr, ...] = ()


class SequentialModelSet(StrictModel):
    champion_policy_id: NonEmptyStr
    retained_policy_ids: tuple[NonEmptyStr, ...]
    comparisons: tuple[PolicyComparison, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method: str = "BONFERRONI_NORMAL_MIXTURE_CS_V1"
    assumptions: tuple[str, ...] = (
        "paired loss differences are conditionally bounded",
        "comparison family is fixed before outcomes",
    )


def compare_policies_anytime(
    observations: tuple[PairedLossObservation, ...],
    policy: SequentialComparisonPolicy,
    offline_model_set: frozenset[str] | None = None,
) -> SequentialModelSet:
    """Compare challengers with a conservative time-uniform Hoeffding CS.

    Lower loss is better. Difference = challenger loss - champion loss, so a
    negative interval supports challenger superiority.
    """

    grouped: dict[tuple[str, str], list[PairedLossObservation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.champion_policy_id, observation.challenger_policy_id)].append(
            observation
        )
    if not grouped:
        raise ValueError("at least one paired comparison is required")
    champion_ids = {key[0] for key in grouped}
    if len(champion_ids) != 1:
        raise ValueError("all comparisons must share one champion")
    if len(grouped) > policy.maximum_family_size:
        raise ValueError("multiplicity family exceeds registered maximum")

    family_size = len(grouped)
    comparisons: list[PolicyComparison] = []
    retained = set(champion_ids)
    for (champion_id, challenger_id), values in sorted(grouped.items()):
        if offline_model_set is not None and challenger_id not in offline_model_set:
            comparisons.append(
                PolicyComparison(
                    champion_policy_id=champion_id,
                    challenger_policy_id=challenger_id,
                    state=ComparisonState.COMPARISON_INVALID,
                    sample_count=0,
                    mean_loss_difference=None,
                    lower_bound=None,
                    upper_bound=None,
                    path=(),
                    reason_codes=("P9_LIVE_POLICY_NOT_IN_OFFLINE_MODEL_SET",),
                )
            )
            continue
        ordered = sorted(values, key=lambda item: (item.cohort_id, item.prediction_event_id))
        if len({(item.cohort_id, item.prediction_event_id) for item in ordered}) != len(ordered):
            raise ValueError("duplicate paired cohort observation")
        differences = [item.challenger_loss - item.champion_loss for item in ordered]
        max_abs = policy.loss_upper_bound - policy.loss_lower_bound
        if any(abs(value) > max_abs + 1e-12 for value in differences):
            comparisons.append(
                PolicyComparison(
                    champion_policy_id=champion_id,
                    challenger_policy_id=challenger_id,
                    state=ComparisonState.COMPARISON_INVALID,
                    sample_count=len(differences),
                    mean_loss_difference=None,
                    lower_bound=None,
                    upper_bound=None,
                    path=(),
                    reason_codes=("P9_LIVE_SEQUENTIAL_LOSS_BOUND_VIOLATION",),
                )
            )
            continue
        path = _confidence_path(differences, policy, family_size)
        final = path[-1]
        if final.sample_count < policy.minimum_samples:
            state = ComparisonState.INSUFFICIENT_EVIDENCE
            reasons = ("P9_LIVE_COMPARISON_INSUFFICIENT_EVIDENCE",)
        elif final.upper_bound < -policy.minimum_effect:
            state = ComparisonState.CHALLENGER_SUPERIOR
            reasons = ()
            retained.add(challenger_id)
        elif final.lower_bound > policy.minimum_effect:
            state = ComparisonState.CHAMPION_SUPERIOR
            reasons = ()
        else:
            state = ComparisonState.STATISTICALLY_INDISTINGUISHABLE
            reasons = ()
            retained.add(challenger_id)
        comparisons.append(
            PolicyComparison(
                champion_policy_id=champion_id,
                challenger_policy_id=challenger_id,
                state=state,
                sample_count=final.sample_count,
                mean_loss_difference=final.mean_loss_difference,
                lower_bound=final.lower_bound,
                upper_bound=final.upper_bound,
                path=tuple(path),
                reason_codes=reasons,
            )
        )

    payload = [comparison.model_dump(mode="json") for comparison in comparisons]
    return SequentialModelSet(
        champion_policy_id=next(iter(champion_ids)),
        retained_policy_ids=tuple(sorted(retained)),
        comparisons=tuple(comparisons),
        result_sha256=payload_sha256(payload),
    )


def _confidence_path(
    differences: list[float],
    policy: SequentialComparisonPolicy,
    family_size: int,
) -> list[TimeUniformPoint]:
    difference_range = 2.0 * (policy.loss_upper_bound - policy.loss_lower_bound)
    variance_proxy = (difference_range * difference_range) / 4.0
    family_alpha = policy.alpha / family_size
    mixture_rho = variance_proxy
    path: list[TimeUniformPoint] = []
    for index in range(1, len(differences) + 1):
        mean = fmean(differences[:index])
        intrinsic_time = variance_proxy * index
        radius = sqrt(
            (intrinsic_time + mixture_rho)
            * log((intrinsic_time + mixture_rho) / (mixture_rho * family_alpha * family_alpha))
        ) / index
        path.append(
            TimeUniformPoint(
                sample_count=index,
                mean_loss_difference=mean,
                lower_bound=mean - radius,
                upper_bound=mean + radius,
            )
        )
    return path
