"""Deterministic identity and inline-reference helpers for P5 V2 publication."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import gennorm, norm, t

from ..domain.core import ArtifactReference
from ..domain.distributions import (
    EmpiricalDistribution,
    ForecastDistribution,
    MixtureDistribution,
    ParametricDistribution,
    PointDistribution,
    QuantileDistribution,
    ScenarioDistribution,
    distribution_cdf,
    point_value,
    quantile_value,
)
from .identifiers import as_utc, stable_hash, stable_id

SCHEMA_VERSION = "2.0.0"


def identity_fields(
    *,
    module_id: str,
    run_id: str,
    cycle_id: str,
    decision_time: str | datetime,
    created_at: str | datetime,
    payload: Any,
    lineage_inputs: Any,
) -> dict[str, Any]:
    decision = as_utc(decision_time)
    created = as_utc(created_at)
    digest = stable_hash(module_id, SCHEMA_VERSION, payload)
    return {
        "artifact_id": stable_id("p5-v2", module_id, digest),
        "artifact_sha256": digest,
        "schema_version": SCHEMA_VERSION,
        "producer_phase": "P5",
        "producer_module_id": module_id,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "decision_time": decision,
        "created_at": created,
        "available_at": created,
        "lineage_id": stable_id("p5-v2-lineage", module_id, lineage_inputs, digest),
    }


def artifact_reference(name: str, artifact: dict[str, Any], *, row_count: int | None = None) -> ArtifactReference:
    digest = str(artifact["artifact_sha256"])
    return ArtifactReference(
        artifact_id=str(artifact["artifact_id"]),
        artifact_type=name,
        storage_uri=f"inline/{name}/{digest}.json",
        content_hash=digest,
        schema_version=str(artifact.get("schema_version", SCHEMA_VERSION)),
        row_count=row_count,
        metadata={
            "producer_phase": "P5",
            "producer_module_id": artifact.get("producer_module_id"),
            "lineage_id": artifact.get("lineage_id"),
            "available_at": artifact.get("available_at"),
        },
    )


def distribution_statistics(distribution: ForecastDistribution) -> dict[str, Any]:
    quantiles = tuple((level, quantile_value(distribution, level)) for level in (0.01, 0.05, 0.50, 0.95, 0.99))
    by_level = dict(quantiles)
    probability_negative = float(np.clip(distribution_cdf(distribution, 0.0), 0.0, 1.0))
    return {
        "mean": distribution_mean(distribution),
        "median": by_level[0.50],
        "mode": distribution_mode(distribution),
        "mode_method": distribution_mode_method(distribution),
        "quantiles": quantiles,
        "probability_positive": 1.0 - probability_negative,
        "probability_negative": probability_negative,
        "tail_probabilities": {
            "probability_below_or_equal_q01": float(np.clip(distribution_cdf(distribution, by_level[0.01]), 0.0, 1.0)),
            "probability_below_or_equal_q05": float(np.clip(distribution_cdf(distribution, by_level[0.05]), 0.0, 1.0)),
            "probability_above_q95": float(np.clip(1.0 - distribution_cdf(distribution, by_level[0.95]), 0.0, 1.0)),
            "probability_above_q99": float(np.clip(1.0 - distribution_cdf(distribution, by_level[0.99]), 0.0, 1.0)),
        },
        "tail_probability_semantics": "CDF_EVALUATED_AT_PUBLISHED_QUANTILES",
        "distribution_family": distribution_family(distribution),
        "support": distribution_support(distribution),
    }


def distribution_mean(distribution: ForecastDistribution) -> float:
    if isinstance(distribution, PointDistribution):
        return distribution.value
    if isinstance(distribution, ParametricDistribution):
        return distribution.location
    if isinstance(distribution, MixtureDistribution):
        return float(sum(item.weight * item.location for item in distribution.components))
    if isinstance(distribution, EmpiricalDistribution):
        return float(np.mean(distribution.samples))
    if isinstance(distribution, ScenarioDistribution):
        return float(sum(item.probability * item.value for item in distribution.scenarios))
    if isinstance(distribution, QuantileDistribution):
        levels = np.asarray([item.level for item in distribution.quantiles], dtype=float)
        values = np.asarray([item.value for item in distribution.quantiles], dtype=float)
        grid = np.linspace(0.001, 0.999, 999)
        return float(np.mean(np.interp(grid, levels, values)))
    return point_value(distribution)


def distribution_mode(distribution: ForecastDistribution) -> float | None:
    if isinstance(distribution, (PointDistribution, ParametricDistribution)):
        return point_value(distribution)
    if isinstance(distribution, MixtureDistribution):
        lower = min(item.location - 12.0 * item.scale for item in distribution.components)
        upper = max(item.location + 12.0 * item.scale for item in distribution.components)
        grid = np.linspace(lower, upper, 4097)
        density = np.asarray([_mixture_pdf(distribution, value) for value in grid], dtype=float)
        peak = int(np.argmax(density))
        left = grid[max(0, peak - 2)]
        right = grid[min(len(grid) - 1, peak + 2)]
        if right <= left:
            return float(grid[peak])
        result = minimize_scalar(lambda value: -_mixture_pdf(distribution, float(value)), bounds=(left, right), method="bounded")
        return float(result.x if result.success else grid[peak])
    return None


def distribution_mode_method(distribution: ForecastDistribution) -> str:
    if isinstance(distribution, PointDistribution):
        return "EXACT_POINT"
    if isinstance(distribution, ParametricDistribution):
        return "EXACT_SYMMETRIC_LOCATION"
    if isinstance(distribution, MixtureDistribution):
        return "NUMERICAL_GLOBAL_GRID_PLUS_BOUNDED_REFINEMENT"
    return "UNAVAILABLE"


def _mixture_pdf(distribution: MixtureDistribution, value: float) -> float:
    total = 0.0
    for item in distribution.components:
        if item.family == "NORMAL":
            density = norm.pdf(value, loc=item.location, scale=item.scale)
        elif item.family == "STUDENT_T":
            density = t.pdf(value, df=item.degrees_of_freedom, loc=item.location, scale=item.scale)
        else:
            density = gennorm.pdf(value, beta=item.shape_parameter, loc=item.location, scale=item.scale)
        total += item.weight * float(density)
    return float(total)


def distribution_family(distribution: ForecastDistribution) -> str:
    if isinstance(distribution, ParametricDistribution):
        return distribution.family
    if isinstance(distribution, MixtureDistribution):
        return "FINITE_MIXTURE"
    return distribution.kind


def distribution_support(distribution: ForecastDistribution) -> tuple[float | None, float | None]:
    if isinstance(distribution, (ParametricDistribution, MixtureDistribution)):
        return None, None
    if isinstance(distribution, PointDistribution):
        return distribution.value, distribution.value
    if isinstance(distribution, QuantileDistribution):
        return distribution.quantiles[0].value, distribution.quantiles[-1].value
    if isinstance(distribution, EmpiricalDistribution):
        return min(distribution.samples), max(distribution.samples)
    values = [item.value for item in distribution.scenarios]
    return min(values), max(values)
