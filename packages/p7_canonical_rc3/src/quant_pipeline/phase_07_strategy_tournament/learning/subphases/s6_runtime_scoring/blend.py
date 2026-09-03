from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from ...domain.canonical import digest
from ...domain.errors import fail
from .contracts import BlendPolicy, ConfidencePolicy

def _index(records: tuple[dict[str, Any], ...], label: str) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        key = (str(row["comparison_group_id"]), str(row["candidate_id"]))
        if key in result:
            fail("P7_LTR_RUNTIME_DUPLICATE_CANDIDATE", f"duplicate {label} {key}")
        result[key] = dict(row)
    return result

def build_hybrid_outputs(
    interpretable_records: tuple[dict[str, Any], ...], decomposition_records: tuple[dict[str, Any], ...],
    calibration_records: tuple[dict[str, Any], ...], confidence_records: tuple[dict[str, Any], ...],
    compatibility_records: tuple[dict[str, Any], ...], blend: BlendPolicy, confidence_policy: ConfidencePolicy,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    interpret = _index(interpretable_records, "interpretable score")
    calibration = _index(calibration_records, "calibration")
    confidence = _index(confidence_records, "confidence")
    decomposition = _index(decomposition_records, "interpretable decomposition")
    compatibility = compatibility_records[0]
    all_keys = sorted(interpret)
    if set(calibration) != set(all_keys) or set(confidence) != set(all_keys) or set(decomposition) != set(all_keys):
        fail("P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED", "Learning inputs do not conserve candidates")
    hybrid: list[dict[str, Any]] = []
    decomposed: list[dict[str, Any]] = []
    conservation: list[dict[str, Any]] = []
    for key in all_keys:
        base = interpret[key]; cal = calibration[key]; conf = confidence[key]; upstream = decomposition[key]
        row, parts = _blend_one(base, cal, conf, compatibility, blend, confidence_policy, upstream)
        hybrid.append(row); decomposed.append(parts)
        conservation.append({
            "comparison_group_id": key[0], "candidate_id": key[1], "input_present": True,
            "output_present": True, "candidate_status": row["hybrid_status"], "reason_code": row["reason_code"],
        })
    return hybrid, decomposed, conservation

def _blend_one(base: Mapping[str, Any], cal: Mapping[str, Any], conf: Mapping[str, Any],
               compatibility: Mapping[str, Any], blend: BlendPolicy, confidence_policy: ConfidencePolicy,
               upstream: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    requested = compatibility["requested_mode"]
    fallback = compatibility["fallback_mode"]
    interpreted = float(base["interpretable_score"])
    calibrated = cal.get("calibrated_ltr_score")
    confidence = conf.get("overall_confidence")
    can_hybrid = (requested == "HYBRID_QUALIFIED" and calibrated is not None and confidence is not None
                  and float(confidence) >= confidence_policy.minimum_hybrid_confidence)
    if can_hybrid:
        effective_ltr = blend.ltr_weight * float(confidence)
        effective_interpretable = 1.0 - effective_ltr
        final = effective_interpretable * interpreted + effective_ltr * float(calibrated)
        status, reason = "HYBRID", "P7_LTR_HYBRID_SCORE_AVAILABLE"
    elif requested == "LTR_SHADOW" or fallback == "INTERPRETABLE_ONLY" or requested == "INTERPRETABLE_ONLY":
        effective_ltr, effective_interpretable, final = 0.0, 1.0, interpreted
        status = "SHADOW" if requested == "LTR_SHADOW" and calibrated is not None else "INTERPRETABLE_FALLBACK"
        reason = "P7_LTR_SHADOW_NO_INFLUENCE" if status == "SHADOW" else "P7_LTR_INTERPRETABLE_FALLBACK"
    else:
        effective_ltr, effective_interpretable, final = 0.0, 0.0, None
        status, reason = "ABSTAINED", "P7_LTR_MODEL_PATH_ABSTAINED"
    row = {
        "candidate_id": base["candidate_id"], "comparison_group_id": base["comparison_group_id"],
        "interpretable_score": interpreted, "calibrated_ltr_score": calibrated, "hybrid_score": final,
        "overall_confidence": confidence, "runtime_mode": requested, "hybrid_status": status,
        "reason_code": reason, "blend_policy_version": blend.policy_version,
        "model_hash": compatibility.get("resolved_model_hash"), "lineage_id": upstream["lineage_id"],
    }
    parts = {
        "candidate_id": base["candidate_id"], "comparison_group_id": base["comparison_group_id"],
        "base_interpretable_weight": blend.interpretable_weight, "base_ltr_weight": blend.ltr_weight,
        "effective_interpretable_weight": effective_interpretable, "effective_ltr_weight": effective_ltr,
        "interpretable_contribution": effective_interpretable * interpreted,
        "ltr_contribution": effective_ltr * float(calibrated) if calibrated is not None else None,
        "confidence_shrinkage": confidence, "upstream_decomposition_hash": digest(upstream),
        "safety_penalty_applied": False, "lineage_id": upstream["lineage_id"],
    }
    return row, parts

def build_handoff_manifest(outputs: Mapping[str, Mapping[str, Any]], *, contract_version: str) -> list[dict[str, Any]]:
    references = [{
        "artifact_name": name, "artifact_id": artifact["artifact_id"],
        "content_sha256": artifact["content_sha256"], "record_count": artifact["record_count"],
        "schema_version": artifact["schema_version"],
    } for name, artifact in sorted(outputs.items())]
    return [{
        "contract_id": "hybrid_scoring_handoff", "contract_version": contract_version,
        "producer_stage": "LEARNING", "consumer_stage": "FINALIZATION",
        "artifact_references": references, "reference_count": len(references),
        "content_sha256": digest(references),
    }]
