"""Leak-safe proper scoring and adaptive conformal calibration."""
from __future__ import annotations

from collections import defaultdict
from math import ceil, log
from typing import Any

import numpy as np
from scipy.stats import kstest, norm

from ..domain.distributions import QuantileDistribution, QuantilePoint, quantile_value
from ..domain.forecast import ForecastMemberPanel, ForecastMemberRecord, OOFValidationObservationPanel
from ..errors import DataQualityError

_MIN_OOF = 12
_EPS = 1e-12


def harmonize(panels: list[ForecastMemberPanel]) -> ForecastMemberPanel:
    records = tuple(record for panel in panels for record in panel.records)
    if not records:
        raise DataQualityError("harmonizer requires at least one non-empty forecast panel")
    economic_units: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in records:
        economic_units[(row.target_id, row.horizon)].add(row.unit)
    incompatible = {key: units for key, units in economic_units.items() if len(units) > 1}
    if incompatible:
        raise DataQualityError(f"incompatible units for target/horizon: {incompatible}")
    return ForecastMemberPanel(records=records)


def score(
    panel: ForecastMemberPanel,
    observations: OOFValidationObservationPanel,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del panel
    validation: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
    calibration: dict[tuple[str, str, str, str], list[Any]] = defaultdict(list)
    for row in observations.records:
        destination = validation if row.partition_id == "VALIDATION" else calibration
        destination[_oof_key(row)].append(row)
    keys = sorted(set(validation) | set(calibration))
    scores = [_score_resolver(key, sorted(validation.get(key, []), key=lambda row: row.prediction_timestamp)) for key in keys]
    diagnostics = [_calibration_resolver(key, sorted(calibration.get(key, []), key=lambda row: row.prediction_timestamp)) for key in keys]
    return {
        "records": scores,
        "partition_scope": "VALIDATION_ONLY",
        "metric_policy": "TARGET_AWARE_PROPER_ROBUST_TAIL_AND_PIT",
    }, {
        "records": diagnostics,
        "partition_scope": "CALIBRATION_ONLY",
        "finite_sample_policy": "CEIL((N+1)*COVERAGE)/N",
    }


def _score_resolver(key: tuple[str, str, str, str], rows: list[Any]) -> dict[str, Any]:
    identity = _identity(key)
    if not rows:
        return {**identity, "status": "NO_OOF", "sample_size": 0}
    if len(rows) < _MIN_OOF:
        return {**identity, "status": "INSUFFICIENT_VALIDATION", "sample_size": len(rows), "partition_scope": "VALIDATION_ONLY"}
    prediction = np.asarray([row.prediction for row in rows], dtype=float)
    realized = np.asarray([row.realized for row in rows], dtype=float)
    errors = realized - prediction
    absolute, squared = np.abs(errors), errors**2
    scale = max(float(np.std(errors, ddof=1)), float(np.median(absolute)), _EPS)
    huber = np.where(absolute <= scale, 0.5 * squared, scale * (absolute - 0.5 * scale))
    direction_mask = (np.abs(realized) > _EPS) | (np.abs(prediction) > _EPS)
    directional = float(np.mean(np.sign(realized[direction_mask]) == np.sign(prediction[direction_mask]))) if np.any(direction_mask) else None
    interval = _interval_metrics([row for row in rows if row.q05 is not None and row.q95 is not None])
    pit = norm.cdf(realized, loc=prediction, scale=scale)
    pit_statistic, pit_pvalue = kstest(pit, "uniform")
    target, unit = key[1].lower(), key[3].lower()
    qlike = _qlike(target, unit, realized, prediction)
    tail = _tail_metrics(rows, realized, prediction)
    return {
        **identity,
        "status": "OK",
        "sample_size": len(rows),
        "mse": float(np.mean(squared)),
        "rmse": float(np.sqrt(np.mean(squared))),
        "mae": float(np.mean(absolute)),
        "huber_loss": float(np.mean(huber)),
        "bias": float(np.mean(errors)),
        "residual_std": scale,
        "directional_accuracy": directional,
        "gaussian_log_score": float(np.mean(0.5 * np.log(2.0 * np.pi * scale**2) + 0.5 * squared / scale**2)),
        "pit_ks_statistic": float(pit_statistic),
        "pit_ks_pvalue": float(pit_pvalue),
        "qlike": qlike,
        **interval,
        **tail,
        "regime_slices": _regime_slices(rows),
        "partition_scope": "VALIDATION_ONLY",
    }


def _interval_metrics(rows: list[Any]) -> dict[str, Any]:
    if not rows:
        return {
            "coverage_90": None, "conditional_coverage_by_regime": [],
            "mean_interval_width": None, "pinball_q05": None, "pinball_q95": None,
            "interval_score_90": None, "crps_quantile_approx": None, "crossing_rate": None,
        }
    coverage = float(np.mean([row.q05 <= row.realized <= row.q95 for row in rows]))
    width = float(np.mean([row.q95 - row.q05 for row in rows]))
    p05 = float(np.mean([_pinball(row.realized, row.q05, 0.05) for row in rows]))
    p95 = float(np.mean([_pinball(row.realized, row.q95, 0.95) for row in rows]))
    p50 = float(np.mean([_pinball(row.realized, row.prediction, 0.50) for row in rows]))
    return {
        "coverage_90": coverage,
        "conditional_coverage_by_regime": _conditional_coverage(rows),
        "mean_interval_width": width,
        "pinball_q05": p05,
        "pinball_q95": p95,
        "interval_score_90": float(np.mean([_interval_score(row.realized, row.q05, row.q95) for row in rows])),
        "crps_quantile_approx": float(2.0 * np.mean([p05, p50, p95])),
        "crossing_rate": float(np.mean([row.q05 > row.q95 for row in rows])),
    }


def _calibration_resolver(key: tuple[str, str, str, str], rows: list[Any]) -> dict[str, Any]:
    identity = _identity(key)
    if not rows:
        return {**identity, "status": "NO_CALIBRATION", "sample_size": 0}
    if len(rows) < _MIN_OOF:
        return {**identity, "status": "INSUFFICIENT_CALIBRATION", "sample_size": len(rows), "partition_scope": "CALIBRATION_ONLY"}
    residuals = np.asarray([row.realized - row.prediction for row in rows], dtype=float)
    absolute = np.abs(residuals)
    nonconformity = np.asarray([
        max(float(row.q05) - row.realized, row.realized - float(row.q95), 0.0)
        if row.q05 is not None and row.q95 is not None else abs(row.realized - row.prediction)
        for row in rows
    ], dtype=float)
    recent = nonconformity[max(0, len(nonconformity) // 2):]
    radius = _finite_sample_quantile(nonconformity, 0.90)
    adaptive = _finite_sample_quantile(recent, 0.90)
    coverage = float(np.mean(absolute <= radius))
    rolling = _rolling_coverage(absolute, radius)
    return {
        **identity,
        "status": "OK",
        "absolute_residual_q90": _finite_sample_quantile(absolute, 0.90),
        "absolute_residual_q95": _finite_sample_quantile(absolute, 0.95),
        "cqr_nonconformity_q90": radius,
        "adaptive_recent_radius_q90": adaptive,
        "regime_radii": _regime_radii(rows),
        "target_coverage": 0.90,
        "realized_coverage": coverage,
        "coverage_drift": coverage - 0.90,
        "rolling_coverage": rolling,
        "mean_interval_width_proxy": float(2.0 * radius),
        "sample_size": len(rows),
        "partition_scope": "CALIBRATION_ONLY",
        "method": "CQR_SPLIT_CONFORMAL_PLUS_ADAPTIVE_RECENT_AND_REGIME_WEIGHTED",
    }


def calibrate(
    panel: ForecastMemberPanel,
    diagnostics: dict[str, Any],
    context_router: dict[str, Any] | None = None,
) -> tuple[ForecastMemberPanel, dict[str, Any]]:
    rows = {
        _diagnostic_key(row): row for row in diagnostics.get("records", [])
        if row.get("status") == "OK" and int(row.get("sample_size", 0)) >= _MIN_OOF
    }
    context = _context_map(context_router)
    calibrated, report = [], []
    for record in panel.records:
        diagnostic = rows.get(_resolver_key(record))
        if diagnostic is None:
            calibrated.append(record.model_copy(update={"status": "DEGRADED"}))
            report.append({"record_id": record.record_id, "resolver_id": record.resolver_id, "status": "NO_CALIBRATION", "eligible_for_ensemble": False})
            continue
        context_row = context.get(_economic_key(record))
        if context_row is None or context_row.get("scenario_width_multiplier") is None:
            calibrated.append(record.model_copy(update={"status": "DEGRADED"}))
            report.append({
                "record_id": record.record_id,
                "resolver_id": record.resolver_id,
                "status": "CONTEXT_UNAVAILABLE",
                "eligible_for_ensemble": False,
                "reason_code": "P5_CONTEXT_UNAVAILABLE",
            })
            continue
        base = max(float(diagnostic["cqr_nonconformity_q90"]), float(diagnostic["adaptive_recent_radius_q90"]))
        regime_radius = _selected_regime_radius(diagnostic, context_row.get("current_regime"))
        if regime_radius is not None:
            base = max(base, regime_radius)
        multiplier = float(context_row["scenario_width_multiplier"])
        radius = base * multiplier
        calibrated.append(_widen(record, radius))
        report.append({
            "record_id": record.record_id,
            "resolver_id": record.resolver_id,
            "base_radius": base,
            "context_multiplier": multiplier,
            "radius": radius,
            "target_coverage": diagnostic["target_coverage"],
            "realized_coverage": diagnostic["realized_coverage"],
            "coverage_drift": diagnostic["coverage_drift"],
            "method": "CQR_ADAPTIVE_REGIME_WEIGHTED_WITH_CONTEXT_WIDENING",
            "status": "CALIBRATED",
            "eligible_for_ensemble": True,
        })
    return ForecastMemberPanel(records=tuple(calibrated)), {
        "records": report,
        "calibration_partition": "CALIBRATION_ONLY",
        "coverage_claim": "MARGINAL_UNDER_EXCHANGEABILITY; ADAPTIVE_AND_REGIME_MODES_ARE_MONITORED",
    }


def _tail_metrics(rows, realized, prediction):
    interval = [row for row in rows if row.q05 is not None]
    if not interval:
        return {"var_95_coverage": None, "var_independence_statistic": None, "es_backtest_mean_excess": None}
    violations = np.asarray([row.realized < row.q05 for row in interval], dtype=bool)
    coverage = float(np.mean(violations))
    independence = _violation_independence(violations)
    losses = -realized
    forecast_losses = -prediction
    threshold = float(np.quantile(forecast_losses, 0.95))
    tail = losses[losses >= threshold]
    return {
        "var_95_coverage": coverage,
        "var_independence_statistic": independence,
        "es_backtest_mean_excess": float(np.mean(tail - threshold)) if len(tail) else 0.0,
    }


def _violation_independence(violations: np.ndarray) -> float:
    if len(violations) < 3:
        return 0.0
    counts = np.ones((2, 2), dtype=float)
    for left, right in zip(violations[:-1].astype(int), violations[1:].astype(int), strict=True):
        counts[left, right] += 1.0
    row_prob = counts / counts.sum(axis=1, keepdims=True)
    unconditional = counts[:, 1].sum() / counts.sum()
    log_independent = np.sum(counts[:, 1] * log(max(unconditional, _EPS)) + counts[:, 0] * log(max(1.0 - unconditional, _EPS)))
    log_markov = np.sum(counts * np.log(np.maximum(row_prob, _EPS)))
    return float(max(0.0, 2.0 * (log_markov - log_independent)))


def _qlike(target, unit, realized, prediction):
    if "variance" not in target and "variance" not in unit:
        return None
    positive_realized = np.maximum(realized, _EPS)
    positive_prediction = np.maximum(prediction, _EPS)
    ratio = positive_realized / positive_prediction
    return float(np.mean(ratio - np.log(ratio) - 1.0))


def _regime_slices(rows):
    output = []
    for regime in sorted({str(row.regime_label) for row in rows if row.regime_label is not None}):
        selected = [row for row in rows if str(row.regime_label) == regime]
        residuals = np.asarray([row.realized - row.prediction for row in selected], dtype=float)
        output.append({"regime_label": regime, "sample_size": len(selected), "mae": float(np.mean(np.abs(residuals))), "rmse": float(np.sqrt(np.mean(residuals**2))), "bias": float(np.mean(residuals))})
    return output


def _conditional_coverage(rows):
    return [
        {"regime_label": regime, "sample_size": len(selected), "coverage_90": float(np.mean([row.q05 <= row.realized <= row.q95 for row in selected]))}
        for regime in sorted({str(row.regime_label) for row in rows if row.regime_label is not None})
        for selected in [[row for row in rows if str(row.regime_label) == regime]]
    ]


def _regime_radii(rows):
    output = []
    for regime in sorted({str(row.regime_label) for row in rows if row.regime_label is not None}):
        values = np.abs(np.asarray([row.realized - row.prediction for row in rows if str(row.regime_label) == regime], dtype=float))
        output.append({"regime_label": regime, "sample_size": len(values), "radius_90": _finite_sample_quantile(values, 0.90)})
    return output


def _rolling_coverage(absolute, radius):
    window = min(20, len(absolute))
    return float(np.mean(absolute[-window:] <= radius))


def _selected_regime_radius(diagnostic, current):
    if not current:
        return None
    for row in diagnostic.get("regime_radii", []):
        if row.get("regime_label") == current and int(row.get("sample_size", 0)) >= 5:
            return float(row["radius_90"])
    return None


def _finite_sample_quantile(values: np.ndarray, coverage: float) -> float:
    ordered = np.sort(np.asarray(values, dtype=float))
    if ordered.size == 0:
        raise DataQualityError("finite-sample quantile requires observations")
    rank = min(ordered.size, max(1, ceil((ordered.size + 1) * coverage)))
    return float(ordered[rank - 1])


def _pinball(realized, forecast, level):
    error = realized - forecast
    return float(max(level * error, (level - 1.0) * error))


def _interval_score(realized, lower, upper, alpha=0.10):
    result = upper - lower
    if realized < lower: result += 2.0 * (lower - realized) / alpha
    elif realized > upper: result += 2.0 * (realized - upper) / alpha
    return float(result)


def _widen(record: ForecastMemberRecord, radius: float) -> ForecastMemberRecord:
    center = record.point_forecast
    lower = min(quantile_value(record.distribution, 0.05), center - radius)
    upper = max(quantile_value(record.distribution, 0.95), center + radius)
    distribution = QuantileDistribution(quantiles=(
        QuantilePoint(level=0.05, value=lower), QuantilePoint(level=0.50, value=center), QuantilePoint(level=0.95, value=upper),
    ))
    return record.model_copy(update={"distribution": distribution, "status": "VALID"})


def _resolver_key(record): return record.resolver_id, record.target_id, record.horizon, record.unit

def _oof_key(row): return row.resolver_id, row.target_id, row.horizon, row.unit

def _economic_key(record): return record.underlying, record.target_id, record.horizon, record.unit

def _identity(key): return {"resolver_id": key[0], "target_id": key[1], "horizon": key[2], "unit": key[3]}


def _diagnostic_key(row):
    required = ("resolver_id", "target_id", "horizon", "unit")
    if any(not str(row.get(name, "")).strip() for name in required):
        raise DataQualityError("scoring diagnostic lacks resolver/target/horizon/unit identity")
    return tuple(str(row[name]) for name in required)


def _context_map(router):
    if not router:
        return {}
    result = {}
    for row in router.get("records", []):
        value = row.get("context_uncertainty")
        if value is not None and (not np.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0):
            raise DataQualityError("context_uncertainty must be finite and between zero and one")
        result[(row["underlying"], row["target_id"], row["horizon"], row["unit"])] = row
    return result
