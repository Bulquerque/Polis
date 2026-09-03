"""Dependency-free walk-forward, ablation and promotion statistics for P3.

This package evaluates artifacts but never promotes them.  Promotion remains an
external P0/P9 decision and the returned report explicitly encodes that boundary.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from enum import StrEnum
from statistics import mean, pstdev
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class Variant(StrEnum):
    SEARCH_RAG = "SEARCH_RAG"
    SINGLE_AGENT = "SINGLE_AGENT"
    SOCIETY_NO_RELATIONS = "SOCIETY_NO_RELATIONS"
    SOCIETY_NO_MEMORY = "SOCIETY_NO_MEMORY"
    SOCIETY_NO_TOOLS = "SOCIETY_NO_TOOLS"
    FULL_SOCIETY = "FULL_SOCIETY"


class EvaluationObservation(StrictModel):
    variant: Variant
    fold_id: str
    seed: int
    returns: tuple[float, ...] = Field(min_length=2)
    latency_ms: float = Field(ge=0.0)
    cost_units: float = Field(ge=0.0)
    pit_integrity: bool
    authority_integrity: bool
    evidence_coverage: float = Field(ge=0.0, le=1.0)


class VariantMetrics(StrictModel):
    variant: Variant
    observation_count: int
    return_count: int
    mean_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    mean_latency_ms: float
    mean_cost_units: float
    mean_evidence_coverage: float
    pit_integrity: bool
    authority_integrity: bool


class PairedComparison(StrictModel):
    candidate: Variant
    baseline: Variant
    mean_sharpe_delta: float
    confidence_low: float
    confidence_high: float
    sign_test_p_value: float
    holm_adjusted_p_value: float
    aligned_pair_count: int


class ScientificEvaluationReport(StrictModel):
    report_version: str = "p3.scientific-evaluation.v1"
    metrics: tuple[VariantMetrics, ...]
    comparisons: tuple[PairedComparison, ...]
    full_society_incremental_value_demonstrated: bool
    guardrails_passed: bool
    promotion_authority: str = "P0_P9_EXTERNAL_ONLY"
    production_promotion_allowed: bool = False
    reason_codes: tuple[str, ...]


def _max_drawdown(values: Iterable[float]) -> float:
    wealth = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in values:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        drawdown = max(drawdown, (peak - wealth) / peak)
    return drawdown


def _sharpe(values: tuple[float, ...], periods_per_year: float = 252.0) -> float:
    sigma = pstdev(values)
    return 0.0 if sigma <= 1e-15 else mean(values) / sigma * math.sqrt(periods_per_year)


def _metrics(variant: Variant, rows: list[EvaluationObservation]) -> VariantMetrics:
    flattened = tuple(value for row in rows for value in row.returns)
    return VariantMetrics(
        variant=variant,
        observation_count=len(rows),
        return_count=len(flattened),
        mean_return=mean(flattened),
        volatility=pstdev(flattened),
        sharpe=_sharpe(flattened),
        max_drawdown=_max_drawdown(flattened),
        mean_latency_ms=mean(row.latency_ms for row in rows),
        mean_cost_units=mean(row.cost_units for row in rows),
        mean_evidence_coverage=mean(row.evidence_coverage for row in rows),
        pit_integrity=all(row.pit_integrity for row in rows),
        authority_integrity=all(row.authority_integrity for row in rows),
    )


def _aligned_sharpe_deltas(candidate: list[EvaluationObservation], baseline: list[EvaluationObservation]) -> tuple[float, ...]:
    candidate_map = {(row.fold_id, row.seed): row for row in candidate}
    baseline_map = {(row.fold_id, row.seed): row for row in baseline}
    keys = sorted(set(candidate_map) & set(baseline_map))
    return tuple(_sharpe(candidate_map[key].returns) - _sharpe(baseline_map[key].returns) for key in keys)


def _bootstrap_ci(values: tuple[float, ...], *, seed: int, samples: int = 2000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = sorted(mean(rng.choice(values) for _ in values) for _ in range(samples))
    return means[int(0.025 * (samples - 1))], means[int(0.975 * (samples - 1))]


def _sign_test(values: tuple[float, ...]) -> float:
    nonzero = [value for value in values if abs(value) > 1e-12]
    n = len(nonzero)
    if n == 0:
        return 1.0
    positives = sum(value > 0 for value in nonzero)
    k = min(positives, n - positives)
    tail = sum(math.comb(n, index) for index in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def _holm_adjust(pairs: list[tuple[Variant, float]]) -> dict[Variant, float]:
    ordered = sorted(pairs, key=lambda item: item[1])
    adjusted: dict[Variant, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (variant, p_value) in enumerate(ordered):
        current = min(1.0, (count - rank) * p_value)
        running = max(running, current)
        adjusted[variant] = running
    return adjusted


def evaluate_ablation(observations: Iterable[EvaluationObservation], *, alpha: float = 0.05) -> ScientificEvaluationReport:
    grouped: dict[Variant, list[EvaluationObservation]] = defaultdict(list)
    for row in observations:
        grouped[row.variant].append(row)
    required = set(Variant)
    missing = sorted(item.value for item in required - set(grouped))
    if missing:
        raise ValueError(f"missing ablation variants: {missing}")
    metrics = tuple(_metrics(variant, grouped[variant]) for variant in Variant)
    raw: list[tuple[Variant, Variant, tuple[float, ...], float, float, float]] = []
    for baseline in Variant:
        if baseline is Variant.FULL_SOCIETY:
            continue
        deltas = _aligned_sharpe_deltas(grouped[Variant.FULL_SOCIETY], grouped[baseline])
        low, high = _bootstrap_ci(deltas, seed=17 + len(raw))
        raw.append((Variant.FULL_SOCIETY, baseline, deltas, low, high, _sign_test(deltas)))
    adjusted = _holm_adjust([(baseline, p_value) for _, baseline, _, _, _, p_value in raw])
    comparisons = tuple(
        PairedComparison(
            candidate=candidate,
            baseline=baseline,
            mean_sharpe_delta=mean(deltas) if deltas else 0.0,
            confidence_low=low,
            confidence_high=high,
            sign_test_p_value=p_value,
            holm_adjusted_p_value=adjusted[baseline],
            aligned_pair_count=len(deltas),
        )
        for candidate, baseline, deltas, low, high, p_value in raw
    )
    guardrails = all(item.pit_integrity and item.authority_integrity for item in metrics)
    full_value = all(item.mean_sharpe_delta > 0 and item.confidence_low > 0 and item.holm_adjusted_p_value <= alpha for item in comparisons)
    reasons: list[str] = []
    if not guardrails:
        reasons.append("GUARDRAIL_FAILURE")
    if not full_value:
        reasons.append("INCREMENTAL_VALUE_NOT_PROVEN")
    if not reasons:
        reasons.append("EVALUATION_PASSED_EXTERNAL_PROMOTION_STILL_REQUIRED")
    return ScientificEvaluationReport(
        metrics=metrics,
        comparisons=comparisons,
        full_society_incremental_value_demonstrated=full_value,
        guardrails_passed=guardrails,
        reason_codes=tuple(reasons),
    )
