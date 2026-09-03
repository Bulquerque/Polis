from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import numpy as np
from ...adapters.runtime_ranker_resolver import resolve_ranker
from ...domain.canonical import digest
from ...domain.errors import fail
from .contracts import CandidateFeatureRecord

def _model_by_hash(records: tuple[dict[str, Any], ...], model_hash: str) -> dict[str, Any]:
    matches = [dict(row) for row in records if row.get("model_hash") == model_hash]
    if len(matches) != 1:
        fail("P7_LTR_RUNTIME_MODEL_NOT_FOUND", "resolved model not uniquely found")
    return matches[0]

def _validate_model_state(model: Mapping[str, Any], feature_count: int) -> None:
    state = model.get("model_state")
    if not isinstance(state, Mapping) or state.get("implementation_id") != model.get("implementation_id"):
        fail("P7_LTR_RUNTIME_MODEL_STATE_INVALID", "model state implementation mismatch")
    for field in ("imputation_medians", "feature_means", "feature_scales", "coefficients"):
        values = np.asarray(state.get(field, []), dtype=float)
        if values.shape != (feature_count,) or not np.all(np.isfinite(values)):
            fail("P7_LTR_RUNTIME_MODEL_STATE_INVALID", f"invalid model state field {field}")
    if np.any(np.asarray(state["feature_scales"], dtype=float) <= 0.0):
        fail("P7_LTR_RUNTIME_MODEL_STATE_INVALID", "feature scales must be positive")

def _matrix(candidates: list[CandidateFeatureRecord], feature_names: list[str]) -> np.ndarray:
    return np.asarray([[np.nan if row.feature_values.get(name) is None else float(row.feature_values[name])
                        for name in feature_names] for row in candidates], dtype=float)

def score_candidates(
    candidate_records: tuple[dict[str, Any], ...], model_records: tuple[dict[str, Any], ...],
    reference_records: tuple[dict[str, Any], ...], compatibility_records: tuple[dict[str, Any], ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = sorted((CandidateFeatureRecord.model_validate(row) for row in candidate_records),
                        key=lambda row: (row.comparison_group_id, row.candidate_id))
    keys = [(row.comparison_group_id, row.candidate_id) for row in candidates]
    if len(keys) != len(set(keys)):
        fail("P7_LTR_RUNTIME_DUPLICATE_CANDIDATE", "duplicate candidate within comparison group")
    compatibility = compatibility_records[0]
    reference = reference_records[0] if reference_records else None
    output: list[dict[str, Any]] = []
    if compatibility["compatibility_status"] != "RESOLVED" or reference is None:
        for row in candidates:
            output.append(_abstained_score(row, compatibility["reason_code"]))
        receipt = [_runtime_receipt(compatibility, len(candidates), 0, len(candidates), None)]
        return output, receipt
    model = _model_by_hash(model_records, str(reference["model_hash"]))
    names = list(model["feature_names"])
    if any(set(row.feature_values) != set(names) for row in candidates):
        fail("P7_LTR_RUNTIME_FEATURE_ORDER_MISMATCH", "runtime feature names differ from frozen model")
    _validate_model_state(model, len(names))
    adapter = resolve_ranker(str(model["implementation_id"]))
    features = _matrix(candidates, names)
    try:
        scores = adapter.predict(features, dict(model["model_state"]))
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
        fail("P7_LTR_RUNTIME_MODEL_STATE_INVALID", f"runtime prediction failed: {exc}")
    if not np.all(np.isfinite(scores)):
        fail("P7_LTR_RUNTIME_NON_FINITE_SCORE", "runtime ranker produced non-finite score")
    for row, score in zip(candidates, scores, strict=True):
        output.append({
            "candidate_id": row.candidate_id, "comparison_group_id": row.comparison_group_id,
            "raw_ltr_score": float(score), "score_status": "SCORED",
            "reason_code": "P7_LTR_RUNTIME_SCORE_AVAILABLE", "model_family_id": model["model_family_id"],
            "implementation_id": model["implementation_id"], "model_hash": model["model_hash"],
            "feature_schema_hash": row.feature_schema_hash, "feature_vector_hash": digest(dict(row.feature_values)),
            "lineage_id": row.lineage_id,
        })
    receipt = [_runtime_receipt(compatibility, len(candidates), len(candidates), 0, model)]
    return output, receipt

def _abstained_score(row: CandidateFeatureRecord, reason_code: str) -> dict[str, Any]:
    return {
        "candidate_id": row.candidate_id, "comparison_group_id": row.comparison_group_id,
        "raw_ltr_score": None, "score_status": "MODEL_PATH_ABSTAINED", "reason_code": reason_code,
        "model_family_id": None, "implementation_id": None, "model_hash": None,
        "feature_schema_hash": row.feature_schema_hash, "feature_vector_hash": digest(dict(row.feature_values)),
        "lineage_id": row.lineage_id,
    }

def _runtime_receipt(compatibility: Mapping[str, Any], total: int, scored: int, abstained: int,
                     model: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "status": "PASS", "compatibility_status": compatibility["compatibility_status"],
        "candidate_count": total, "scored_count": scored, "abstained_count": abstained,
        "fit_performed": False, "calibration_fit_performed": False,
        "model_hash": model.get("model_hash") if model else None,
        "implementation_id": model.get("implementation_id") if model else None,
        "deterministic": True,
    }
