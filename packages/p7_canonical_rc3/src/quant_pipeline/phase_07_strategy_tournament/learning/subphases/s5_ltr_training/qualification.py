from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ...domain.models import QualificationStatus
from ...domain.ranking_metrics import aggregate_metrics, metrics_by_query


class QualificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    k: int = Field(ge=1)
    min_validation_queries: int = Field(ge=1)
    min_calibration_queries: int = Field(ge=1)
    min_folds: int = Field(ge=1)
    min_ndcg: float = Field(ge=0.0, le=1.0)
    min_ndcg_improvement: float
    max_regret_delta: float
    max_fold_ndcg_std: float = Field(ge=0.0)
    max_training_seconds: float = Field(gt=0.0)
    champion_ndcg_improvement: float = 0.05
    allow_champion_recommendation: bool = False
    min_slice_queries: int = Field(default=1, ge=1)
    min_slice_ndcg: float = Field(default=0.0, ge=0.0, le=1.0)
    max_slice_regret: float = Field(default=1.0, ge=0.0)
    max_calibration_mae: float = Field(default=1.0, ge=0.0)


def _rows_by_model(records: tuple[dict[str, Any], ...], split: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["split"] == "TEST":
            raise ValueError("TEST scores are forbidden in qualification evidence")
        if row["split"] == split:
            model_hash = str(row.get("model_hash", ""))
            if not model_hash:
                raise ValueError("qualification evidence requires exact model_hash")
            result[model_hash].append(dict(row))
    return result


def _slice_metrics(rows: list[dict[str, Any]], policy: QualificationPolicy) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("objective_family", "regime"):
        values = sorted({str(row[field]) for row in rows if row.get(field) is not None})
        result[field] = {}
        for value in values:
            slice_rows = [row for row in rows if str(row.get(field)) == value]
            metrics = aggregate_metrics(metrics_by_query(slice_rows, score_field="raw_ltr_score", k=policy.k))
            metrics["query_count"] = len({str(row["query_id"]) for row in slice_rows})
            result[field][value] = metrics
    return result


def _metric_summary(rows: list[dict[str, Any]], policy: QualificationPolicy) -> dict[str, Any]:
    folds = sorted({str(row["fold_id"]) for row in rows})
    model = aggregate_metrics(metrics_by_query(rows, score_field="raw_ltr_score", k=policy.k))
    baseline = aggregate_metrics(metrics_by_query(rows, score_field="interpretable_score", k=policy.k))
    fold_ndcg = [
        aggregate_metrics(metrics_by_query(
            [row for row in rows if row["fold_id"] == fold], score_field="raw_ltr_score", k=policy.k
        ))["ndcg_at_k"]
        for fold in folds
    ]
    return {
        "folds": folds,
        "query_count": len({str(row["query_id"]) for row in rows}),
        "model": model,
        "baseline": baseline,
        "ndcg_improvement": model["ndcg_at_k"] - baseline["ndcg_at_k"],
        "regret_delta": model["regret_at_k"] - baseline["regret_at_k"],
        "fold_ndcg_std": float(np.std(fold_ndcg)) if fold_ndcg else 0.0,
        "slice_metrics": _slice_metrics(rows, policy),
    }


def _calibration_summary(rows: list[dict[str, Any]], model: Mapping[str, Any]) -> dict[str, Any]:
    scores = np.asarray([float(row["raw_ltr_score"]) for row in rows], dtype=float)
    labels = np.asarray([float(row["utility_label"]) for row in rows], dtype=float)
    calibrator = model.get("calibrator", {})
    finite = bool(np.isfinite(scores).all() and np.isfinite(labels).all())
    slope = float(calibrator.get("slope", 0.0))
    intercept = float(calibrator.get("intercept", 0.0))
    predicted = slope * scores + intercept
    mae = float(np.mean(np.abs(predicted - labels))) if len(rows) and finite else None
    return {
        "query_count": len({str(row["query_id"]) for row in rows}),
        "record_count": len(rows),
        "finite": finite,
        "calibrator_status": str(calibrator.get("status", "UNAVAILABLE")),
        "slope": slope,
        "intercept": intercept,
        "mean_absolute_error": mae,
    }



def _slice_gate_summary(summary: Mapping[str, Any], policy: QualificationPolicy) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for dimension, slices in summary.get("slice_metrics", {}).items():
        for slice_value, metrics in slices.items():
            query_count = int(metrics.get("query_count", 0))
            ndcg = float(metrics.get("ndcg_at_k", 0.0))
            regret = float(metrics.get("regret_at_k", float("inf")))
            checks = {
                "sufficient_queries": query_count >= policy.min_slice_queries,
                "minimum_ndcg": ndcg >= policy.min_slice_ndcg,
                "maximum_regret": regret <= policy.max_slice_regret,
            }
            decisions.append({
                "dimension": dimension,
                "slice_value": slice_value,
                "query_count": query_count,
                "ndcg_at_k": ndcg,
                "regret_at_k": regret,
                "checks": checks,
                "passed": all(checks.values()),
            })
    return {
        "policy": {
            "min_slice_queries": policy.min_slice_queries,
            "min_slice_ndcg": policy.min_slice_ndcg,
            "max_slice_regret": policy.max_slice_regret,
        },
        "decisions": decisions,
        "passed": bool(decisions) and all(row["passed"] for row in decisions),
    }

def _gates(
    summary: Mapping[str, Any], calibration: Mapping[str, Any], model: Mapping[str, Any],
    receipt: Mapping[str, Any], policy: QualificationPolicy,
) -> dict[str, bool]:
    slice_summary = _slice_gate_summary(summary, policy)
    return {
        "sufficient_queries": int(summary["query_count"]) >= policy.min_validation_queries,
        "sufficient_folds": len(summary["folds"]) >= policy.min_folds,
        "absolute_ndcg": float(summary["model"]["ndcg_at_k"]) >= policy.min_ndcg,
        "baseline_ndcg": float(summary["ndcg_improvement"]) >= policy.min_ndcg_improvement,
        "baseline_regret": float(summary["regret_delta"]) <= policy.max_regret_delta,
        "fold_stability": float(summary["fold_ndcg_std"]) <= policy.max_fold_ndcg_std,
        "calibration_evidence": int(calibration["query_count"]) >= policy.min_calibration_queries,
        "calibrator_ready": calibration["calibrator_status"] == "CALIBRATED" and bool(calibration["finite"]),
        "calibration_quality": calibration.get("mean_absolute_error") is not None
        and float(calibration["mean_absolute_error"]) <= policy.max_calibration_mae,
        "slice_quality": bool(slice_summary["passed"]),
        "resource_budget": bool(receipt.get("resource_budget_compliant", False))
        and float(receipt.get("resource_budget_seconds", float("inf"))) <= policy.max_training_seconds,
        "deterministic": bool(receipt.get("deterministic", False)) and bool(model.get("deterministic", False)),
    }


def _status(gates: Mapping[str, bool], improvement: float, policy: QualificationPolicy) -> tuple[str, str]:
    evidence = ("sufficient_queries", "sufficient_folds", "calibration_evidence")
    if not all(gates[key] for key in evidence):
        return QualificationStatus.INSUFFICIENT_EVIDENCE.value, "P7_LTR_MODEL_INSUFFICIENT_EVIDENCE"
    if not all(gates.values()):
        quality = {"baseline_ndcg", "baseline_regret"}
        if all(value for key, value in gates.items() if key not in quality):
            return QualificationStatus.SHADOW.value, "P7_LTR_MODEL_FAILED_BASELINE_GATE"
        return QualificationStatus.REJECTED.value, "P7_LTR_MODEL_UNSTABLE"
    if policy.allow_champion_recommendation and improvement >= policy.champion_ndcg_improvement:
        return QualificationStatus.CHAMPION.value, "P7_LTR_MODEL_CHAMPION_RECOMMENDED"
    return QualificationStatus.QUALIFIED_CHALLENGER.value, "P7_LTR_MODEL_QUALIFIED"


def _records(
    model: Mapping[str, Any], summary: Mapping[str, Any], calibration: Mapping[str, Any],
    gates: Mapping[str, bool], status: str, reason: str, policy: QualificationPolicy,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = {
        "model_family_id": model["model_family_id"], "model_hash": model["model_hash"], "status": status,
        "reason_code": reason, "query_count": summary["query_count"], "fold_count": len(summary["folds"]),
        "model_metrics": summary["model"], "interpretable_baseline_metrics": summary["baseline"],
        "ndcg_improvement": summary["ndcg_improvement"], "regret_delta": summary["regret_delta"],
        "fold_ndcg_std": summary["fold_ndcg_std"], "slice_metrics": summary["slice_metrics"],
        "slice_gate_summary": _slice_gate_summary(summary, policy),
        "calibration_summary": dict(calibration), "gate_results": dict(gates),
        "promotion_authority": "P0_MODEL_REGISTRY",
    }
    eligible = status in {QualificationStatus.CHAMPION.value, QualificationStatus.QUALIFIED_CHALLENGER.value}
    registry = {
        "model_family_id": model["model_family_id"], "model_hash": model["model_hash"],
        "qualification_status": status, "reason_code": reason, "target_id": model["target_id"],
        "target_policy_version": model["target_policy_version"], "feature_schema_hash": model["feature_schema_hash"],
        "training_cutoff_at": model["training_cutoff_at"], "runtime_eligible": eligible,
        "calibrator_status": calibration["calibrator_status"], "promotion_status": "NOT_PROMOTED",
    }
    return report, registry


def qualify_models(
    model_records: tuple[dict[str, Any], ...], oof_records: tuple[dict[str, Any], ...],
    calibration_records: tuple[dict[str, Any], ...], execution_records: tuple[dict[str, Any], ...],
    policy: QualificationPolicy,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    execution = {str(row["model_hash"]): row for row in execution_records}
    validation = _rows_by_model(oof_records, "VALIDATION")
    calibration = _rows_by_model(calibration_records, "CALIBRATION")
    reports: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    for model in sorted(model_records, key=lambda row: str(row["model_family_id"])):
        model_id = str(model["model_hash"])
        summary = _metric_summary(validation.get(model_id, []), policy)
        calibration_summary = _calibration_summary(calibration.get(model_id, []), model)
        gates = _gates(summary, calibration_summary, model, execution.get(model_id, {}), policy)
        status, reason = _status(gates, float(summary["ndcg_improvement"]), policy)
        report, entry = _records(model, summary, calibration_summary, gates, status, reason, policy)
        reports.append(report)
        registry.append(entry)
    return reports, registry
