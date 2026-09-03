"""Fold-aware proper-score summaries and baseline-controlled qualification."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from scipy.stats import ttest_rel

from ..domain.forecast import OOFValidationObservationPanel
from ..errors import QualificationError, ReasonCode


def validation_summary(panel: OOFValidationObservationPanel) -> dict[str, Any]:
    grouped: dict[str, list] = defaultdict(list)
    for row in panel.records:
        if row.partition_id == "VALIDATION":
            grouped[row.resolver_id].append(row)
    records = [_resolver_metrics(resolver_id, rows) for resolver_id, rows in sorted(grouped.items())]
    return {"records": records, "test_holdout_used": False, "proper_score_version": "P5-RC34-W3-V2"}


def qualify_models(
    trained: list[dict[str, Any]], validation: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics = {row["resolver_id"]: row for row in validation}
    baseline = _baseline_models(trained, metrics)
    adjusted = _holm_degradation_pvalues(trained, metrics, baseline)
    prelim: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for model in trained:
        row = metrics.get(model["resolver_id"])
        reasons = _failure_reasons(model, row, baseline, adjusted)
        if reasons:
            rejected.append({
                "resolver_id": model["resolver_id"],
                "classification": "INSUFFICIENT_EVIDENCE" if _insufficient(reasons) else "REJECTED",
                "reason_codes": reasons,
            })
        else:
            prelim.append({**model, "metrics": row})
    if not prelim:
        raise QualificationError("qualification rejected every resolver")
    accepted = _classify(prelim)
    promotion = [
        {
            "resolver_id": row["resolver_id"],
            "classification": row["qualification"],
            "target_id": row["target_id"],
            "horizon": row["horizon"],
            "sealed_test_used": False,
            "research_qualified": True,
            "economic_promotion_eligible": bool(
                row["metrics"].get("sample_size", 0) >= 100
                and row["metrics"].get("fold_count", 0) >= 3
                and row["metrics"].get("coverage_90_nominal_supported", False)
            ),
            "promotion_reason_code": (
                "P5_PROSPECTIVE_EVIDENCE_REQUIRED"
                if not (
                    row["metrics"].get("sample_size", 0) >= 100
                    and row["metrics"].get("fold_count", 0) >= 3
                    and row["metrics"].get("coverage_90_nominal_supported", False)
                )
                else None
            ),
        }
        for row in accepted
    ]
    return accepted, rejected, promotion


def _resolver_metrics(resolver_id: str, rows: list) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.fold_id, row.prediction_timestamp, row.underlying))
    errors = np.asarray([row.realized - row.prediction for row in ordered], dtype=float)
    losses = errors**2
    interval_scores = np.asarray([_interval_score(row) for row in ordered], dtype=float)
    fold_losses: dict[str, list[float]] = defaultdict(list)
    for row, loss in zip(ordered, losses, strict=True):
        fold_losses[row.fold_id].append(float(loss))
    fold_mse = {name: float(np.mean(values)) for name, values in sorted(fold_losses.items())}
    lower, upper = _mean_interval(losses)
    coverage = float(np.mean([row.q05 <= row.realized <= row.q95 for row in ordered]))
    coverage_lower, coverage_upper = _wilson_interval(coverage, len(ordered))
    denominator = max(float(np.mean(list(fold_mse.values()))), 1e-12)
    return {
        "resolver_id": resolver_id,
        "scope": "MULTIFOLD_VALIDATION_ONLY_TEST_HOLDOUT_SEALED",
        "partitions": ["VALIDATION"],
        "sample_size": len(ordered),
        "fold_count": len(fold_mse),
        "fold_mse": fold_mse,
        "fold_mse_std": float(np.std(list(fold_mse.values()), ddof=0)),
        "fold_mse_cv": float(np.std(list(fold_mse.values()), ddof=0) / denominator),
        "mse": float(np.mean(losses)),
        "mse_ci_lower": lower,
        "mse_ci_upper": upper,
        "mae": float(np.mean(np.abs(errors))),
        "robust_loss": float(np.mean(np.where(np.abs(errors) <= 0.01, 0.5 * errors**2, 0.01 * (np.abs(errors) - 0.005)))),
        "bias": float(np.mean(errors)),
        "directional_accuracy": float(np.mean([
            np.sign(row.prediction) == np.sign(row.realized) for row in ordered
        ])),
        "coverage_90": coverage,
        "coverage_90_ci_lower": coverage_lower,
        "coverage_90_ci_upper": coverage_upper,
        "coverage_90_nominal_supported": bool(coverage_lower <= 0.90 <= coverage_upper),
        "pinball_q05": float(np.mean([_pinball(row.realized, row.q05, 0.05) for row in ordered])),
        "pinball_q95": float(np.mean([_pinball(row.realized, row.q95, 0.95) for row in ordered])),
        "interval_score_90": float(np.mean(interval_scores)),
        "observation_keys": [
            f"{row.fold_id}|{row.prediction_timestamp.isoformat()}|{row.underlying}" for row in ordered
        ],
        "squared_losses": losses.tolist(),
    }


def _failure_reasons(model, metrics, baseline, adjusted):
    reasons: list[str] = []
    if metrics is None:
        return [ReasonCode.NO_OOF_EVIDENCE.value]
    if int(metrics.get("sample_size", 0)) < 12 or int(metrics.get("fold_count", 0)) < 2:
        reasons.append(ReasonCode.INSUFFICIENT_HISTORY.value)
    if not np.isfinite(float(metrics.get("mse", np.inf))):
        reasons.append(ReasonCode.NO_OOF_EVIDENCE.value)
    coverage = float(metrics.get("coverage_90", -1.0))
    sample_size = int(metrics.get("sample_size", 0))
    ci_lower = float(metrics.get("coverage_90_ci_lower", coverage))
    ci_upper = float(metrics.get("coverage_90_ci_upper", coverage))
    if coverage < 0.0 or coverage > 1.0:
        reasons.append(ReasonCode.MODEL_NOT_CALIBRATED.value)
    elif sample_size >= 30 and coverage < 0.50:
        # A model with extremely poor interval coverage is not even research-ready.
        # Failure to statistically support the nominal 90% level is handled by
        # the separate economic-promotion gate and must not erase all challengers.
        reasons.append(ReasonCode.MODEL_NOT_CALIBRATED.value)
    if float(metrics.get("fold_mse_cv", np.inf)) > 2.0:
        reasons.append(ReasonCode.MODEL_FAILED_BASELINE_GATE.value)
    reference = baseline.get((model["target_id"], model["horizon"]))
    if reference is None:
        reasons.append(ReasonCode.MODEL_FAILED_BASELINE_GATE.value)
    elif model["resolver_family"] != "BASELINE":
        tolerance = float(reference["metrics"]["mse"]) * 1.10
        pvalue = adjusted.get(model["resolver_id"], 1.0)
        if float(metrics["mse"]) > tolerance and pvalue < 0.05:
            reasons.append(ReasonCode.MODEL_FAILED_BASELINE_GATE.value)
    return sorted(set(reasons))


def _baseline_models(trained, metrics):
    output = {}
    for model in trained:
        row = metrics.get(model["resolver_id"])
        if model["resolver_family"] == "BASELINE" and row is not None:
            output[(model["target_id"], model["horizon"])] = {"model": model, "metrics": row}
    return output


def _holm_degradation_pvalues(trained, metrics, baseline):
    raw: list[tuple[str, float]] = []
    for model in trained:
        if model["resolver_family"] == "BASELINE" or model["resolver_id"] not in metrics:
            continue
        reference = baseline.get((model["target_id"], model["horizon"]))
        if reference is None:
            continue
        challenger = metrics[model["resolver_id"]]
        base = reference["metrics"]
        if challenger["observation_keys"] != base["observation_keys"]:
            raw.append((model["resolver_id"], 1.0))
            continue
        left = np.asarray(challenger["squared_losses"], dtype=float)
        right = np.asarray(base["squared_losses"], dtype=float) * 1.10
        result = ttest_rel(left, right, alternative="greater")
        raw.append((model["resolver_id"], float(result.pvalue) if np.isfinite(result.pvalue) else 1.0))
    ordered = sorted(raw, key=lambda item: item[1])
    count = len(ordered)
    return {identifier: min(1.0, pvalue * (count - index)) for index, (identifier, pvalue) in enumerate(ordered)}


def _classify(models):
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for model in models:
        grouped[(model["target_id"], model["horizon"])].append(model)
    output = []
    for rows in grouped.values():
        ordered = sorted(rows, key=lambda row: (row["metrics"]["mse"], row["resolver_id"]))
        champion_id = ordered[0]["resolver_id"]
        for row in ordered:
            classification = "CHAMPION" if row["resolver_id"] == champion_id else "QUALIFIED_CHALLENGER"
            output.append({**row, "qualification": classification})
    return output


def _mean_interval(values: np.ndarray) -> tuple[float, float]:
    mean = float(np.mean(values))
    if len(values) < 2:
        return mean, mean
    radius = 1.96 * float(np.std(values, ddof=1)) / np.sqrt(len(values))
    return max(0.0, mean - radius), mean + radius


def _wilson_interval(success_rate: float, sample_size: int, z: float = 1.96) -> tuple[float, float]:
    if sample_size <= 0:
        return 0.0, 1.0
    p = min(max(float(success_rate), 0.0), 1.0)
    denominator = 1.0 + z * z / sample_size
    center = (p + z * z / (2.0 * sample_size)) / denominator
    radius = z * np.sqrt((p * (1.0 - p) + z * z / (4.0 * sample_size)) / sample_size) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _interval_score(row) -> float:
    width = float(row.q95 - row.q05)
    penalty = 0.0
    if row.realized < row.q05:
        penalty = 20.0 * float(row.q05 - row.realized)
    elif row.realized > row.q95:
        penalty = 20.0 * float(row.realized - row.q95)
    return width + penalty


def _pinball(realized: float, prediction: float, level: float) -> float:
    error = realized - prediction
    return max(level * error, (level - 1.0) * error)


def _insufficient(reasons: list[str]) -> bool:
    return any(reason in {ReasonCode.INSUFFICIENT_HISTORY.value, ReasonCode.NO_OOF_EVIDENCE.value} for reason in reasons)
