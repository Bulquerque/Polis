"""Paired evaluation of real pipeline observations under a frozen protocol."""
from __future__ import annotations

import math
import random
from collections.abc import Callable
from statistics import mean

from .hashing import sha256_value
from .models import EvaluationObservation, EvaluationObservationPanel, ExperimentRegistry

BASELINES = (
    "SEARCH_RAG",
    "SINGLE_AGENT",
    "SOCIETY_NO_RELATIONS",
    "SOCIETY_NO_MEMORY",
    "SOCIETY_NO_TOOLS",
)

METRIC_GETTERS: dict[str, tuple[Callable[[EvaluationObservation], float], bool]] = {
    "brier_score": (lambda row: row.brier_score, False),
    "log_loss": (lambda row: row.log_loss, False),
    "net_return": (lambda row: row.net_return, True),
    "max_drawdown": (lambda row: row.max_drawdown, False),
    "evidence_coverage": (lambda row: row.evidence_coverage, True),
    "cost": (lambda row: row.cost, False),
    "latency_ms": (lambda row: row.latency_ms, False),
}


def _paired(
    rows: tuple[EvaluationObservation, ...],
    candidate: str,
    baseline: str,
    getter: Callable[[EvaluationObservation], float],
    *,
    higher: bool,
) -> tuple[float, ...]:
    index = {(row.variant, row.fold_id, row.seed): row for row in rows}
    candidate_keys = {
        (row.fold_id, row.seed) for row in rows if row.variant == candidate
    }
    baseline_keys = {
        (row.fold_id, row.seed) for row in rows if row.variant == baseline
    }
    keys = sorted(candidate_keys & baseline_keys)
    sign = 1.0 if higher else -1.0
    return tuple(
        sign
        * (
            getter(index[(candidate, *key)])
            - getter(index[(baseline, *key)])
        )
        for key in keys
    )


def _bootstrap(
    values: tuple[float, ...], *, seed: int, samples: int = 5000
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    estimates = sorted(
        mean(rng.choice(values) for _ in values) for _ in range(samples)
    )
    return (
        estimates[int(0.025 * (samples - 1))],
        estimates[int(0.975 * (samples - 1))],
    )


def _sign_p(values: tuple[float, ...]) -> float:
    nonzero = tuple(value for value in values if abs(value) > 1e-12)
    if not nonzero:
        return 1.0
    positives = sum(value > 0 for value in nonzero)
    count = len(nonzero)
    tail = min(positives, count - positives)
    return min(
        1.0,
        2.0
        * sum(math.comb(count, index) for index in range(tail + 1))
        / (2**count),
    )


def _holm(items: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(items, key=lambda item: item[1])
    result: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for index, (name, probability) in enumerate(ordered):
        running = max(running, min(1.0, (count - index) * probability))
        result[name] = running
    return result


def evaluate_real_observations(
    panel: EvaluationObservationPanel,
    registry: ExperimentRegistry,
) -> dict[str, object]:
    if panel.experiment_id != registry.experiment_id:
        raise ValueError("observation panel experiment mismatch")
    if panel.experiment_registry_hash != registry.registry_hash:
        raise ValueError("observation panel registry hash mismatch")
    expected_pairs = len(registry.seeds) * len(
        {(row.fold_id) for row in panel.observations}
    )
    raw: list[dict[str, object]] = []
    for threshold in registry.primary_metrics:
        getter, higher = METRIC_GETTERS[threshold.metric]
        for baseline in BASELINES:
            deltas = _paired(
                panel.observations,
                "FULL_SOCIETY",
                baseline,
                getter,
                higher=higher,
            )
            low, high = _bootstrap(
                deltas,
                seed=int(
                    sha256_value(
                        {
                            "experiment_id": registry.experiment_id,
                            "metric": threshold.metric,
                            "baseline": baseline,
                        }
                    )[:8],
                    16,
                ),
            )
            probability = _sign_p(deltas)
            raw.append(
                {
                    "metric": threshold.metric,
                    "baseline": baseline,
                    "deltas": deltas,
                    "mean_delta": mean(deltas) if deltas else 0.0,
                    "ci_low": low,
                    "ci_high": high,
                    "p_value": probability,
                    "minimum_delta": threshold.minimum_delta,
                    "alpha": threshold.alpha,
                    "guardrail": threshold.guardrail,
                    "expected_pairs": expected_pairs,
                }
            )
    adjusted = _holm(
        [
            (f"{item['metric']}::{item['baseline']}", float(item["p_value"]))
            for item in raw
        ]
    )
    comparisons: list[dict[str, object]] = []
    passed = bool(raw)
    for item in raw:
        key = f"{item['metric']}::{item['baseline']}"
        holm_p = adjusted[key]
        aligned_pairs = len(item["deltas"])
        comparison = {name: value for name, value in item.items() if name != "deltas"}
        comparison["aligned_pairs"] = aligned_pairs
        comparison["holm_p_value"] = holm_p
        comparison["passed"] = (
            aligned_pairs == item["expected_pairs"]
            and float(item["ci_low"]) >= float(item["minimum_delta"])
            and holm_p <= float(item["alpha"])
        )
        passed = passed and bool(comparison["passed"])
        comparisons.append(comparison)
    report = {
        "report_version": "p3.scientific-evaluation.v2",
        "release_id": registry.release_id,
        "release_sha256": registry.release_sha256,
        "experiment_id": panel.experiment_id,
        "experiment_registry_hash": registry.registry_hash,
        "observation_panel_hash": panel.panel_hash,
        "comparisons": comparisons,
        "all_preregistered_comparisons_passed": passed,
        "source_kind": "REAL_PIPELINE_ONLY",
        "promotion_authority": "P0_ONLY",
        "production_promotion_allowed": False,
    }
    report["report_hash"] = sha256_value(report)
    return report
