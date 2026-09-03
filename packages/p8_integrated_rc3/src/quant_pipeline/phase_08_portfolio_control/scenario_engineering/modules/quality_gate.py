"""P8.S3.M03 scenario calibration and quality gate."""
from __future__ import annotations

import numpy as np

from ..arrays import ScenarioSet
from ..contracts import (
    QualityAssessment,
    QualityMetric,
    QualityPolicy,
    QualityStatus,
    RealizedSamplePanel,
)
from ..errors import ContractIntegrityError, TemporalIntegrityError

MODULE_ID = "P8.S3.M03"


def _relative_norm(left: np.ndarray, right: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(right)), 1e-12)
    return float(np.linalg.norm(left - right) / denominator)


def _validated_samples(
    scenarios: ScenarioSet,
    realized: RealizedSamplePanel,
) -> np.ndarray:
    if realized.available_at > realized.decision_time:
        raise TemporalIntegrityError("realized samples were not available at decision time")
    if realized.factor_ids != scenarios.factor_ids:
        raise ContractIntegrityError("realized factor registry differs from scenarios")
    samples = np.asarray(realized.samples, dtype=np.float64)
    if samples.ndim != 2 or samples.shape[1] != len(scenarios.factor_ids):
        raise ContractIntegrityError("realized samples shape mismatch")
    return samples


def _metric_inputs(
    scenario_terminal: np.ndarray,
    samples: np.ndarray,
) -> dict[str, float | bool]:
    mean_error = _relative_norm(scenario_terminal.mean(axis=0), samples.mean(axis=0))
    scenario_cov = np.atleast_2d(np.cov(scenario_terminal, rowvar=False))
    realized_cov = np.atleast_2d(np.cov(samples, rowvar=False))
    covariance_error = _relative_norm(scenario_cov, realized_cov)
    levels = np.asarray([0.05, 0.50, 0.95])
    scenario_q = np.quantile(scenario_terminal, levels, axis=0)
    realized_q = np.quantile(samples, levels, axis=0)
    scale = np.maximum(np.abs(realized_q), np.std(samples, axis=0)[None, :] + 1e-12)
    quantile_error = float(np.mean(np.abs(scenario_q - realized_q) / scale))
    tail_scale = np.maximum(
        np.abs(realized_q[[0, 2]]),
        np.std(samples, axis=0)[None, :] + 1e-12,
    )
    tail_error = float(
        np.mean(np.abs(scenario_q[[0, 2]] - realized_q[[0, 2]]) / tail_scale)
    )
    return {
        "sample_count": float(len(samples)),
        "mean_error": mean_error,
        "covariance_error": covariance_error,
        "quantile_error": quantile_error,
        "tail_error": tail_error,
    }


def _quality_metrics(
    values: dict[str, float | bool],
    policy: QualityPolicy,
) -> tuple[list[QualityMetric], dict[str, bool]]:
    enough = float(values["sample_count"]) >= policy.minimum_realized_samples
    passed = {
        "enough": enough,
        "mean": float(values["mean_error"]) <= policy.mean_relative_error_max,
        "covariance": float(values["covariance_error"]) <= policy.covariance_relative_error_max,
        "quantile": float(values["quantile_error"]) <= policy.quantile_absolute_error_max,
        "tail": float(values["tail_error"]) <= policy.tail_quantile_error_max,
    }
    specifications = (
        ("mean_relative_error", "mean_error", policy.mean_relative_error_max, "mean"),
        ("covariance_relative_error", "covariance_error", policy.covariance_relative_error_max, "covariance"),
        ("quantile_absolute_error", "quantile_error", policy.quantile_absolute_error_max, "quantile"),
        ("tail_quantile_error", "tail_error", policy.tail_quantile_error_max, "tail"),
    )
    metrics = [QualityMetric(
        name="realized_sample_count",
        value=float(values["sample_count"]),
        threshold=float(policy.minimum_realized_samples),
        passed=enough,
        reason_code=None if enough else "INSUFFICIENT_REALIZED_SAMPLES",
    )]
    metrics.extend(QualityMetric(
        name=name, value=float(values[key]), threshold=threshold, passed=passed[passed_key]
    ) for name, key, threshold, passed_key in specifications)
    return metrics, passed


def _build_metrics(
    scenario_terminal: np.ndarray,
    samples: np.ndarray,
    policy: QualityPolicy,
) -> tuple[list[QualityMetric], dict[str, bool]]:
    return _quality_metrics(_metric_inputs(scenario_terminal, samples), policy)

def _family_status(
    family: str,
    path_count: int,
    policy: QualityPolicy,
    passed: dict[str, bool],
) -> QualityStatus:
    if not passed["enough"]:
        return QualityStatus.NOT_ACTIONABLE
    if family in policy.require_paths_for_families and path_count == 1:
        return QualityStatus.PATH_INCOMPLETE
    if not passed["tail"]:
        return QualityStatus.TAIL_INCOMPLETE
    if passed["mean"] and passed["covariance"] and passed["quantile"]:
        return QualityStatus.FULLY_QUALIFIED
    if passed["mean"] and passed["quantile"]:
        return QualityStatus.QUALIFIED_WITH_HAIRCUT
    return QualityStatus.NOT_ACTIONABLE


def _missing_assessment(
    strategy_families: tuple[str, ...],
    policy: QualityPolicy,
) -> QualityAssessment:
    statuses = {family: QualityStatus.NOT_ACTIONABLE for family in strategy_families}
    metric = QualityMetric(
        name="realized_sample_count",
        value=None,
        threshold=float(policy.minimum_realized_samples),
        passed=False,
        reason_code="REALIZED_SAMPLES_UNAVAILABLE",
    )
    return QualityAssessment(
        status_by_family=statuses,
        score=0.0,
        metrics=(metric,),
        reason_codes=("REALIZED_SAMPLES_UNAVAILABLE",),
    )


def assess_quality(
    scenarios: ScenarioSet,
    realized: RealizedSamplePanel | None,
    strategy_families: tuple[str, ...],
    policy: QualityPolicy,
) -> QualityAssessment:
    if realized is None:
        return _missing_assessment(strategy_families, policy)
    samples = _validated_samples(scenarios, realized)
    metrics, passed = _build_metrics(scenarios.values[:, -1, :], samples, policy)
    statuses = {
        family: _family_status(family, scenarios.shape[1], policy, passed)
        for family in strategy_families
    }
    score = sum(metric.passed is True for metric in metrics) / len(metrics)
    reasons = tuple(sorted({metric.reason_code for metric in metrics if metric.reason_code}))
    return QualityAssessment(
        status_by_family=statuses,
        score=score,
        metrics=tuple(metrics),
        reason_codes=reasons,
    )
