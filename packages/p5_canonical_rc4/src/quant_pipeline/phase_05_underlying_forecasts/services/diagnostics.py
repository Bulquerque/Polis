"""Changepoint, OOD, disagreement and calibrated context diagnostics."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance
from sklearn.covariance import LedoitWolf

from ..domain.forecast import ForecastMemberPanel, OOFValidationObservationPanel
from ..errors import DataQualityError
from .identifiers import stable_id
from .regime import infer_regime

_EPS = 1e-12

def recurrent_regime(values: np.ndarray) -> dict[str, Any]:
    return infer_regime(_series(values, minimum=24))

def page_hinkley(values: np.ndarray, delta: float = 0.005, threshold: float = 0.05) -> dict[str, Any]:
    array = _series(values, minimum=12)
    ph = _page_hinkley(array, delta, threshold)
    cusum = _cusum(array)
    split = max(6, len(array) // 2)
    early, late = array[:split], array[split:]
    distribution = float(wasserstein_distance(early, late) / max(np.std(array), 1e-8))
    volatility = float(abs(np.std(late) - np.std(early)) / max(np.std(early), 1e-8))
    detectors = {
        "page_hinkley": float(ph["maximum_score"] / max(threshold, 1e-8)),
        "cusum": float(cusum["score"] / 5.0),
        "distribution_shift": distribution,
        "volatility_shift": volatility,
    }
    alarms = {name: value >= 1.0 for name, value in detectors.items()}
    consensus = sum(alarms.values())
    probability = float(1.0 - np.exp(-np.mean(list(detectors.values()))))
    return {
        **ph,
        "alarm": consensus >= 2,
        "change_point_probability": float(np.clip(probability, 0.0, 1.0)),
        "cusum_score": float(cusum["score"]),
        "cusum_alarm": bool(cusum["alarm"]),
        "detector_scores": detectors,
        "detector_alarms": alarms,
        "detector_consensus": consensus,
        "method": "PAGE_HINKLEY_CUSUM_DISTRIBUTION_VOLATILITY_CONSENSUS",
        "dependence_shift_status": "UNAVAILABLE_IN_UNIVARIATE_MODULE",
        "parameters": {
            "page_hinkley_delta": float(delta),
            "page_hinkley_threshold": float(threshold),
            "cusum_reference_z": 5.0,
            "distribution_shift_alarm": 1.0,
            "volatility_shift_alarm": 1.0,
        },
    }

def ood_score(reference: np.ndarray, current: np.ndarray) -> dict[str, Any]:
    if reference.ndim != 2:
        raise DataQualityError("OOD reference must be a two-dimensional matrix")
    minimum_rows = max(12, 5 * reference.shape[1])
    if len(reference) < minimum_rows or not np.all(np.isfinite(reference)):
        raise DataQualityError(
            f"OOD reference requires at least {minimum_rows} finite rows for {reference.shape[1]} features"
        )
    if current.shape != (reference.shape[1],) or not np.all(np.isfinite(current)):
        raise DataQualityError("OOD current vector must align with reference features")
    estimator = LedoitWolf().fit(reference)
    mean, covariance = estimator.location_, estimator.covariance_
    inverse = np.linalg.pinv(covariance)
    reference_delta = reference - mean
    distances = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", reference_delta, inverse, reference_delta), 0.0))
    delta = current - mean
    mahalanobis = float(np.sqrt(max(delta @ inverse @ delta, 0.0)))
    threshold = float(np.quantile(distances, 0.99))
    empirical_p = float((1 + np.sum(distances >= mahalanobis)) / (len(distances) + 1))
    scale = np.maximum(np.std(reference, axis=0), 1e-8)
    standardized = np.abs(delta) / scale
    contributions = standardized / max(float(np.sum(standardized)), _EPS)
    ratio = mahalanobis / max(threshold, 1e-8)
    return {
        "mahalanobis_distance": mahalanobis,
        "empirical_threshold_99": threshold,
        "empirical_tail_probability": empirical_p,
        "maximum_standardized_shift": float(np.max(standardized)),
        "ood_score": float(np.clip(1.0 - empirical_p, 0.0, 1.0)),
        "ood_flag": bool(mahalanobis > threshold),
        "severity": _severity(ratio),
        "severity_ratio": float(ratio),
        "shrinkage_method": "LEDOIT_WOLF",
        "feature_contributions": contributions.tolist(),
        "reference_sample_size": len(reference),
        "minimum_reference_rows": minimum_rows,
        "feature_dimension": reference.shape[1],
        "threshold_calibration": "EMPIRICAL_REFERENCE_Q99",
    }

def disagreement(
    panels: list[ForecastMemberPanel],
    perspective_context: dict[str, Any] | None = None,
    observations: OOFValidationObservationPanel | None = None,
) -> dict[str, Any]:
    grouped: dict[tuple[Any, ...], list[tuple[str, str, str, float]]] = defaultdict(list)
    for panel in panels:
        for record in panel.records:
            key = (record.as_of_time, record.prediction_timestamp, record.underlying, record.target_id, record.horizon, record.unit)
            grouped[key].append((record.record_id, record.resolver_id, record.resolver_family, record.point_forecast))
    profiles = _residual_profiles(observations)
    records = [_disagreement_record(key, members, perspective_context, profiles) for key, members in sorted(grouped.items())]
    if not records:
        raise DataQualityError("disagreement analysis requires at least one forecast member")
    return {"records": records, "aggregation_grain": "UNDERLYING_TARGET_HORIZON_UNIT"}

def route_context(
    regime: dict[str, Any],
    break_report: dict[str, Any],
    ood: dict[str, Any],
    disagreement_panel: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    records = [_context_record(row, regime, break_report, ood) for row in disagreement_panel.get("records", [])]
    if not records:
        raise DataQualityError("context routing requires disagreement records")
    threshold = 0.75
    router = {
        "policy_version": "RC34-CONTEXT-FAIL-CLOSED-V4",
        "abstain_threshold": threshold,
        "threshold_method": "FROZEN_POLICY_THRESHOLD",
        "minimum_component_weight_coverage": 0.75,
        "records": [_router_record(row, threshold) for row in records],
    }
    evaluation = {
        "regime_labels": regime.get("regime_labels", ()),
        "transition_matrix": regime.get("transition_matrix", []),
        "expected_duration": regime.get("expected_duration", {}),
        "evaluate_transitions_separately": True,
        "regime_model": regime.get("selected_method"),
    }
    return {"records": records}, router, evaluation

def _disagreement_record(key, members, perspective_context, profiles):
    values = np.asarray([item[3] for item in members], dtype=float)
    resolver_ids = [item[1] for item in members]
    cofailure, residual_correlation = _cofailure_metrics(resolver_ids, profiles, key[2], key[3], key[4], key[5])
    median = float(np.median(values))
    multi_member = len(values) >= 2
    crisis = (
        float(np.mean(np.abs(values - median) > max(np.std(values), 1e-8)))
        if multi_member else None
    )
    sign_balance = float(abs(np.mean(np.sign(values)))) if multi_member else None
    return {
        "record_id": stable_id("disagreement", key, members),
        "as_of_time": key[0].isoformat(),
        "prediction_timestamp": key[1].isoformat(),
        "underlying": key[2], "target_id": key[3], "horizon": key[4], "unit": key[5],
        "member_count": len(members),
        "disagreement_status": "AVAILABLE" if multi_member else "UNAVAILABLE",
        "disagreement_reason_code": None if multi_member else "P5_DISAGREEMENT_SINGLE_MEMBER",
        "forecast_dispersion": float(np.std(values, ddof=0)) if multi_member else None,
        "forecast_spread": float(np.max(values) - np.min(values)) if multi_member else None,
        "sign_disagreement": float(1.0 - sign_balance) if multi_member else None,
        "tail_disagreement": (
            float(np.quantile(values, 0.95) - np.quantile(values, 0.05))
            if multi_member else None
        ),
        "residual_correlation": residual_correlation,
        "cofailure_rate": cofailure,
        "crisis_disagreement": crisis,
        "member_ids": [item[0] for item in members],
        "resolver_ids": resolver_ids,
        "resolver_families": sorted({item[2] for item in members}),
        "p4_perspective_conflicts": _perspective_values(perspective_context, key[2], key[4]),
    }

def _context_record(row, regime, break_report, ood):
    probabilities = _regime_probabilities(regime)
    components = {
        "disagreement": _optional_score(row.get("sign_disagreement"), "sign_disagreement"),
        "cofailure": _optional_score(row.get("cofailure_rate"), "cofailure_rate"),
        "ood": _ood_for_underlying(ood, row.get("underlying")),
        "perspective_conflict": _perspective_conflict(row.get("p4_perspective_conflicts", [])),
        "structural_break": _optional_score(break_report.get("change_point_probability"), "change_point_probability"),
        "regime_uncertainty": None if not probabilities else 1.0 - max(probabilities.values()),
    }
    weights = {"disagreement": 0.20, "cofailure": 0.15, "ood": 0.25, "perspective_conflict": 0.10, "structural_break": 0.20, "regime_uncertainty": 0.10}
    uncertainty, effective_weights, weight_coverage = _weighted_context(components, weights)
    missing = tuple(sorted(name for name, value in components.items() if value is None))
    if weight_coverage < 0.75:
        uncertainty = None
    return {
        **row,
        "current_regime": regime.get("current_regime") if probabilities else None,
        "regime_probabilities": probabilities,
        "structural_break_score": break_report.get("score"),
        "change_point_probability": components["structural_break"],
        "ood_score": components["ood"],
        "context_components": components,
        "context_policy_weights": effective_weights,
        "configured_policy_weights": weights,
        "component_weight_coverage": weight_coverage,
        "context_uncertainty": uncertainty,
        "context_status": "AVAILABLE" if not missing else "DEGRADED" if uncertainty is not None else "UNAVAILABLE",
        "missing_components": missing,
    }

def _router_record(row, threshold):
    uncertainty = row["context_uncertainty"]
    unavailable = uncertainty is None or threshold is None
    abstain = unavailable or uncertainty >= threshold
    return {
        "underlying": row["underlying"], "target_id": row["target_id"],
        "horizon": row["horizon"], "unit": row["unit"],
        "recommended_action": "ABSTAIN" if abstain else "ALLOW",
        "context_uncertainty": uncertainty,
        "scenario_width_multiplier": None if unavailable else 1.0 + uncertainty,
        "confidence_shrinkage": None if unavailable else 1.0 - 0.75 * uncertainty,
        "ambiguity_radius_multiplier": None if unavailable else 1.0 + 1.5 * uncertainty,
        "model_eligibility": "RESTRICT" if abstain else "NORMAL",
        "reason_code": (
            "P5_CONTEXT_UNAVAILABLE" if unavailable
            else "P5_CONTEXT_UNCERTAINTY_HIGH" if abstain
            else None
        ),
    }

def _page_hinkley(values, delta, threshold):
    mean = cumulative = minimum = 0.0
    scores, alarms = [], []
    for index, value in enumerate(values, start=1):
        mean += (float(value) - mean) / index
        cumulative += float(value) - mean - delta
        minimum = min(minimum, cumulative)
        score = cumulative - minimum
        scores.append(score)
        if score > threshold:
            alarms.append(index - 1)
            cumulative = minimum = 0.0
    return {"score": float(scores[-1]), "maximum_score": float(max(scores)), "alarm_indices": alarms}

def _cusum(values):
    baseline = values[: max(4, len(values) // 2)]
    mean, scale = float(np.mean(baseline)), max(float(np.std(baseline, ddof=0)), 1e-8)
    positive = negative = maximum = 0.0
    for value in (values - mean) / scale:
        positive = max(0.0, positive + float(value) - 0.5)
        negative = min(0.0, negative + float(value) + 0.5)
        maximum = max(maximum, positive, abs(negative))
    return {"score": float(maximum), "alarm": bool(maximum > 5.0)}

def _residual_profiles(observations):
    result: dict[tuple[str, str, str, str, str], dict[Any, float]] = defaultdict(dict)
    if observations is None:
        return result
    for row in observations.records:
        key = (row.resolver_id, row.underlying, row.target_id, row.horizon, row.unit)
        result[key][row.prediction_timestamp] = float(row.realized - row.prediction)
    return result

def _cofailure_metrics(resolver_ids, profiles, underlying, target, horizon, unit):
    timestamp_sets = [set(profiles.get((resolver, underlying, target, horizon, unit), {})) for resolver in resolver_ids]
    timestamps = set.intersection(*timestamp_sets) if timestamp_sets and all(timestamp_sets) else set()
    if len(timestamps) < 8:
        return None, None
    ordered = sorted(timestamps)
    matrix = np.column_stack([
        [profiles[(resolver, underlying, target, horizon, unit)][value] for value in ordered]
        for resolver in resolver_ids
    ])
    scale = np.maximum(np.std(matrix, axis=0), 1e-8)
    failures = np.abs(matrix) > 1.5 * scale
    cofailure = float(np.mean(np.sum(failures, axis=1) >= max(2, matrix.shape[1] // 2 + 1)))
    if matrix.shape[1] == 1:
        return cofailure, None
    triangle = np.corrcoef(matrix, rowvar=False)[np.triu_indices(matrix.shape[1], 1)]
    return cofailure, float(np.mean(np.abs(triangle)))

def _perspective_values(context, underlying, horizon):
    if not context:
        return []
    output = []
    for row in context.get("records", []):
        if row.get("underlying") != underlying:
            continue
        row_horizon = str(row.get("horizon") or row.get("horizon_group") or "")
        if row_horizon and row_horizon not in {horizon, "CROSS_HORIZON"}:
            continue
        if row.get("conflict_score") is None:
            continue
        output.append({"group_id": row.get("conflict_group_id") or row.get("group_id"), "horizon": row_horizon or None, "score": _bounded_score(row["conflict_score"], name="conflict_score")})
    return output

def _bounded_score(value, *, name):
    score = float(value)
    if not np.isfinite(score) or not 0.0 <= score <= 1.0:
        raise DataQualityError(f"{name} must be finite and between zero and one")
    return score

def _ood_for_underlying(ood, underlying):
    matching = []
    for row in ood.get("records", []):
        if row.get("underlying") != underlying:
            continue
        value = row.get("market_state_ood", row.get("ood_score"))
        if value is not None:
            matching.append(_bounded_score(value, name="market_state_ood"))
    return float(np.mean(matching)) if matching else None

def _optional_score(value, name):
    return None if value is None else _bounded_score(value, name=name)

def _perspective_conflict(conflicts):
    values = [_optional_score(item.get("score"), "conflict_score") for item in conflicts]
    available = [value for value in values if value is not None]
    return max(available) if available else None

def _regime_probabilities(regime):
    raw = regime.get("probabilities")
    if not isinstance(raw, dict) or not raw:
        return {}
    values = {str(name): _bounded_score(value, name="regime_probability") for name, value in raw.items()}
    if abs(sum(values.values()) - 1.0) > 1e-8:
        raise DataQualityError("regime probabilities must sum to one")
    return values

def _weighted_context(components, weights):
    available = {name: value for name, value in components.items() if value is not None}
    if not available:
        return None, {}, 0.0
    covered_weight = float(sum(weights[name] for name in available))
    effective = {name: weights[name] / covered_weight for name in available}
    value = float(np.clip(sum(effective[name] * available[name] for name in available), 0.0, 1.0))
    return value, effective, covered_weight

def _severity(ratio):
    if ratio >= 2.0: return "SEVERE"
    if ratio >= 1.0: return "ELEVATED"
    if ratio >= 0.75: return "WATCH"
    return "NORMAL"

def _series(values, minimum):
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < minimum or not np.all(np.isfinite(array)):
        raise DataQualityError(f"diagnostic requires {minimum} finite observations")
    return array
