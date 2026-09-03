from __future__ import annotations

from collections import defaultdict
from time import monotonic
from typing import Any, Iterable

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ...adapters.numpy_pairwise_ranker import PairwiseLinearRanker
from ...adapters.numpy_pointwise_ranker import PointwiseRidgeRanker
from ...domain.canonical import digest
from ...domain.errors import fail
from ...feature_spec import canonical_feature_names
from ...ports import Ranker


class ModelFamilyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_family_id: str
    enabled: bool = True
    implementation_id: str
    algorithm: str
    hyperparameters: dict[str, float | int]


class ResearchBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    timeout_seconds: float = Field(gt=0)
    max_models: int = Field(ge=1)


def _ranker(record: ModelFamilyRecord) -> Ranker:
    params = record.hyperparameters
    if record.algorithm == "PAIRWISE_LINEAR_RANKNET":
        return PairwiseLinearRanker(
            alpha=float(params.get("alpha", 1.0)), max_iterations=int(params.get("max_iterations", 100)),
            tolerance=float(params.get("tolerance", 1e-8)), label_tolerance=float(params.get("label_tolerance", 1e-12)),
            max_pairs_per_query=int(params.get("max_pairs_per_query", 128)),
            max_pairs_total=int(params.get("max_pairs_total", 100_000)),
        )
    if record.algorithm == "POINTWISE_RIDGE":
        return PointwiseRidgeRanker(alpha=float(params.get("alpha", 1.0)))
    fail("P7_LTR_MODEL_FAMILY_INVALID", f"unsupported algorithm {record.algorithm}")


def _feature_names(records: tuple[dict[str, Any], ...]) -> list[str]:
    names = sorted({name for record in records for name in record["feature_values"]})
    if not names:
        fail("P7_LTR_FEATURE_SCHEMA_MISMATCH", "training dataset contains no features")
    return list(canonical_feature_names(names))


def _matrix(records: Iterable[dict[str, Any]], names: list[str]) -> np.ndarray:
    return np.asarray([[np.nan if row["feature_values"].get(name) is None else float(row["feature_values"][name])
                        for name in names] for row in records], dtype=float)


def _fit(adapter: Ranker, rows: list[dict[str, Any]], names: list[str]) -> dict[str, object]:
    return adapter.fit(
        _matrix(rows, names), np.asarray([float(row["utility_label"]) for row in rows], dtype=float),
        [str(row["query_id"]) for row in rows], [str(row["candidate_id"]) for row in rows],
    )


def _fit_calibrator(scores: np.ndarray, labels: np.ndarray) -> dict[str, float | str]:
    if len(scores) < 2 or float(np.var(scores)) <= 1e-12:
        intercept = float(np.mean(labels)) if len(labels) else 0.0
        return {"status": "UNAVAILABLE", "slope": 0.0, "intercept": intercept}
    covariance = float(np.mean((scores - scores.mean()) * (labels - labels.mean())))
    slope = max(0.0, covariance / float(np.var(scores)))
    return {"status": "CALIBRATED" if slope > 0 else "DEGRADED", "slope": slope,
            "intercept": float(labels.mean() - slope * scores.mean())}


def _score_rows(
    family: ModelFamilyRecord, fold: dict[str, Any], split: str, rows: list[dict[str, Any]],
    names: list[str], adapter: Ranker, state: dict[str, object],
) -> list[dict[str, Any]]:
    scores = adapter.predict(_matrix(rows, names), state)
    return [{
        "model_family_id": family.model_family_id, "implementation_id": state["implementation_id"],
        "fold_id": fold["fold_id"], "split": split, "query_id": row["query_id"],
        "candidate_id": row["candidate_id"], "raw_ltr_score": float(score),
        "utility_label": float(row["utility_label"]), "interpretable_score": float(row["interpretable_score"]),
        "objective_family": row["objective_family"], "candidate_topology": row["candidate_topology"],
        "regime": row["regime"],
    } for row, score in zip(rows, scores, strict=True)]


def _fold_evidence(
    family: ModelFamilyRecord, adapter: Ranker, fold: dict[str, Any], rows_by_query: dict[str, list[dict[str, Any]]],
    names: list[str], started: float, budget: ResearchBudget,
) -> list[dict[str, Any]]:
    forbidden = set(fold["sealed_test_query_ids"])
    used = set(fold["train_query_ids"]) | set(fold["validation_query_ids"]) | set(fold["calibration_query_ids"])
    if forbidden & used:
        fail("P7_LTR_TEST_SEAL_VIOLATION", "sealed TEST query entered training or scoring")
    train_rows = [row for query in fold["train_query_ids"] for row in rows_by_query[query]]
    if len({row["query_id"] for row in train_rows}) < 2:
        fail("P7_LTR_INSUFFICIENT_QUERIES", "fold requires at least two training queries")
    state = _fit(adapter, train_rows, names)
    evidence: list[dict[str, Any]] = []
    for split, field in (("VALIDATION", "validation_query_ids"), ("CALIBRATION", "calibration_query_ids")):
        rows = [row for query in fold[field] for row in rows_by_query[query]]
        evidence.extend(_score_rows(family, fold, split, rows, names, adapter, state))
    if monotonic() - started > budget.timeout_seconds:
        fail("P7_LTR_TRAINING_TIMEOUT", "research budget timeout exceeded")
    return evidence


def _final_artifact(
    family: ModelFamilyRecord, adapter: Ranker, latest: dict[str, Any], rows_by_query: dict[str, list[dict[str, Any]]],
    names: list[str], schema_hash: str, calibration: list[dict[str, Any]], training_cutoff_at: str,
) -> dict[str, Any]:
    query_ids = list(latest["train_query_ids"]) + list(latest["validation_query_ids"])
    rows = [row for query in query_ids for row in rows_by_query[query]]
    state = _fit(adapter, rows, names)
    calibration_rows = [row for row in calibration if row["model_family_id"] == family.model_family_id
                        and row["fold_id"] == latest["fold_id"]]
    calibrator = _fit_calibrator(
        np.asarray([float(row["raw_ltr_score"]) for row in calibration_rows]),
        np.asarray([float(row["utility_label"]) for row in calibration_rows]),
    )
    result = {
        "model_family_id": family.model_family_id, "implementation_id": state["implementation_id"],
        "model_version": "1.0.0", "target_id": rows[0]["target_id"],
        "target_policy_version": rows[0]["target_policy_version"], "feature_schema_hash": schema_hash,
        "feature_names": names, "training_cutoff_at": training_cutoff_at,
        "training_query_ids": sorted(query_ids), "calibration_query_ids": sorted(latest["calibration_query_ids"]),
        "sealed_test_query_ids": sorted(latest["sealed_test_query_ids"]), "model_state": state,
        "calibrator": calibrator, "deterministic": True, "serialization_format": "DECLARATIVE_JSON",
        "promotion_status": "UNQUALIFIED",
    }
    result["model_hash"] = digest(result)
    return result


def _train_family(
    family: ModelFamilyRecord, folds: tuple[dict[str, Any], ...], rows_by_query: dict[str, list[dict[str, Any]]],
    names: list[str], schema_hash: str, budget: ResearchBudget, started: float, training_cutoff_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    adapter = _ranker(family)
    evidence: list[dict[str, Any]] = []
    for fold in folds:
        evidence.extend(_fold_evidence(family, adapter, fold, rows_by_query, names, started, budget))
    calibration = [row for row in evidence if row["split"] == "CALIBRATION"]
    artifact = _final_artifact(family, adapter, folds[-1], rows_by_query, names, schema_hash, calibration, training_cutoff_at)
    for row in evidence:
        row["model_hash"] = artifact["model_hash"]
    receipt = {
        "model_family_id": family.model_family_id, "status": "TRAINED",
        "resource_budget_seconds": budget.timeout_seconds,
        "resource_budget_compliant": monotonic() - started <= budget.timeout_seconds,
        "fold_count": len(folds), "oof_record_count": len(evidence), "feature_count": len(names),
        "deterministic": True, "model_hash": artifact["model_hash"],
    }
    return artifact, evidence, receipt


def train_models(
    dataset_records: tuple[dict[str, Any], ...], fold_records: tuple[dict[str, Any], ...],
    family_records: tuple[dict[str, Any], ...], budget: ResearchBudget, *, seed: int, training_cutoff_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    del seed
    started = monotonic()
    names = _feature_names(dataset_records)
    schema_hashes = {str(row["feature_schema_hash"]) for row in dataset_records}
    if len(schema_hashes) != 1:
        fail("P7_LTR_FEATURE_SCHEMA_MISMATCH", "multiple feature schema hashes")
    rows_by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in dataset_records:
        rows_by_query[str(row["query_id"])].append(dict(row))
    families = sorted((ModelFamilyRecord.model_validate(row) for row in family_records if row.get("enabled", True)),
                      key=lambda item: item.model_family_id)[:budget.max_models]
    if not families:
        fail("P7_LTR_MODEL_FAMILY_INVALID", "no enabled model family")
    artifacts: list[dict[str, Any]] = []
    oof: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for family in families:
        artifact, evidence, receipt = _train_family(
            family, fold_records, rows_by_query, names, next(iter(schema_hashes)), budget, started, training_cutoff_at
        )
        artifacts.append(artifact); oof.extend(evidence); receipts.append(receipt)
    calibration = [row for row in oof if row["split"] == "CALIBRATION"]
    return artifacts, oof, calibration, receipts
