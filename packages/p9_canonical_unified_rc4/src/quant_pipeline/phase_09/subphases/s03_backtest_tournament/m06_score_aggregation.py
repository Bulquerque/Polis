"""P9.S3.M06 — multi-fold and regime score aggregation."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median

import numpy as np

from .common import content_sha256
from .reason_codes import ReasonCode
from .scoring_models import (
    ComparisonLossRecord,
    ConfigurationScoreAggregate,
    FoldWeightPolicy,
    ScoreAggregationPolicy,
    ScoreAggregationResult,
    ScoreContext,
)


def aggregate_scores(
    records: tuple[ScoreContext, ...],
    policy: ScoreAggregationPolicy,
    *,
    expected_fold_ids: tuple[str, ...],
) -> ScoreAggregationResult:
    if not expected_fold_ids or len(expected_fold_ids) != len(set(expected_fold_ids)):
        raise ValueError("expected_fold_ids must be unique and non-empty")

    grouped: dict[tuple[str, str], list[ScoreContext]] = defaultdict(list)
    for item in records:
        grouped[(item.score.configuration_id, item.cohort_id)].append(item)

    aggregates: list[ConfigurationScoreAggregate] = []
    losses: list[ComparisonLossRecord] = []
    global_reasons: set[str] = set()
    expected = set(expected_fold_ids)

    for (configuration_id, cohort_id), items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: (item.score.fold_id, item.score.trial_id))
        folds = [item.score.fold_id for item in items]
        if len(folds) != len(set(folds)):
            raise ValueError("duplicate configuration/fold score")
        scores = [item.score.score for item in items]
        actual_folds = set(folds)
        coverage = Decimal(len(actual_folds & expected)) / Decimal(len(expected))
        reason_codes: list[str] = []
        status = "QUALIFIED"
        if not actual_folds.issubset(expected):
            status = "INVALID"
            reason_codes.append(ReasonCode.AGGREGATION_COHORT_MISMATCH.value)
        if coverage < policy.minimum_fold_coverage:
            status = "INSUFFICIENT_EVIDENCE"
            reason_codes.append(ReasonCode.INSUFFICIENT_FOLD_COVERAGE.value)
        global_reasons.update(reason_codes)

        score_array = np.array([float(value) for value in scores], dtype=np.float64)
        if policy.weight_policy is FoldWeightPolicy.EQUAL_FOLD:
            weights = [Decimal("1") for _ in items]
        else:
            weights = [Decimal(item.score.observation_count) for item in items]
            if sum(weights) <= 0:
                raise ValueError(ReasonCode.WEIGHT_POLICY_INVALID.value)
        weighted_numerator = sum(
            (score * weight for score, weight in zip(scores, weights, strict=True)),
            Decimal("0"),
        )
        weighted = weighted_numerator / sum(weights)
        aggregate = ConfigurationScoreAggregate(
            configuration_id=configuration_id,
            cohort_id=cohort_id,
            fold_count=len(actual_folds),
            expected_fold_count=len(expected),
            coverage=coverage,
            mean_score=sum(scores, Decimal("0")) / Decimal(len(scores)),
            median_score=Decimal(str(median(scores))),
            worst_score=min(scores),
            score_std=Decimal(str(float(np.std(score_array, ddof=0)))),
            weighted_mean_score=weighted,
            status=status,
            reason_codes=tuple(reason_codes),
        )
        aggregates.append(aggregate)
        for item in items:
            losses.append(
                ComparisonLossRecord(
                    configuration_id=configuration_id,
                    cohort_id=cohort_id,
                    unit_id=item.score.fold_id,
                    loss=-item.score.score,
                )
            )

    body = {
        "policy_id": policy.policy_id,
        "aggregates": tuple(aggregates),
        "loss_series": tuple(
            sorted(
                losses,
                key=lambda item: (
                    item.configuration_id,
                    item.cohort_id,
                    item.unit_id,
                ),
            )
        ),
        "reason_codes": tuple(sorted(global_reasons)),
    }
    return ScoreAggregationResult(
        **body,
        content_sha256=content_sha256(body),
    )
