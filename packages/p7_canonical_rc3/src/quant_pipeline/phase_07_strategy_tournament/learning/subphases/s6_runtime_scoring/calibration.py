from __future__ import annotations
from typing import Any
from ...domain.errors import fail
from .contracts import CandidateFeatureRecord, ConfidencePolicy


def _by_candidate(records: tuple[dict[str, Any], ...], name: str) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        key = (str(row["comparison_group_id"]), str(row["candidate_id"]))
        if key in result:
            fail("P7_LTR_RUNTIME_DUPLICATE_CANDIDATE", f"duplicate {name} record {key}")
        result[key] = dict(row)
    return result


def _resolved_evidence(
    model_records: tuple[dict[str, Any], ...],
    reference_records: tuple[dict[str, Any], ...],
    qualification_reports: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reference = reference_records[0] if reference_records else None
    if reference is None:
        return None, None
    model_hash = reference["model_hash"]
    model = next((dict(row) for row in model_records if row.get("model_hash") == model_hash), None)
    report = next((dict(row) for row in qualification_reports if row.get("model_hash") == model_hash), None)
    return model, report


def _validate_evidence(model: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if report.get("status") not in {"CHAMPION", "QUALIFIED_CHALLENGER"}:
        fail("P7_LTR_RUNTIME_QUALIFICATION_EVIDENCE_INVALID", "qualification report is not runtime eligible")
    gates = report.get("gate_results")
    if not isinstance(gates, dict) or not all(bool(value) for value in gates.values()):
        fail("P7_LTR_RUNTIME_QUALIFICATION_EVIDENCE_INVALID", "qualification gates do not close")
    calibrator = model["calibrator"]
    if calibrator.get("status") != "CALIBRATED":
        fail("P7_LTR_RUNTIME_CALIBRATOR_INCOMPATIBLE", "resolved model calibrator is not calibrated")
    return calibrator


def _confidence_values(
    candidate: CandidateFeatureRecord,
    report: dict[str, Any],
    policy: ConfidencePolicy,
) -> tuple[dict[str, float | None], float | None, list[str], dict[str, str], float]:
    calibration_count = int(report["calibration_summary"]["query_count"])
    fold_std = float(report["fold_ndcg_std"])
    components: dict[str, float | None] = {
        "calibration_evidence": min(1.0, calibration_count / policy.min_calibration_queries),
        "fold_stability": max(0.0, 1.0 - fold_std / policy.max_fold_ndcg_std),
        "data_quality": candidate.data_quality_score,
        "ood": None if candidate.ood_score is None else 1.0 - candidate.ood_score,
    }
    missing = sorted(name for name in policy.required_components if components.get(name) is None)
    reasons = {name: f"P7_CONFIDENCE_COMPONENT_{name.upper()}_UNAVAILABLE" for name in missing}
    available_required = [components.get(name) for name in policy.required_components if components.get(name) is not None]
    coverage = len(available_required) / len(policy.required_components) if policy.required_components else 1.0
    overall = None
    if coverage >= policy.minimum_component_coverage and available_required:
        overall = min(float(value) for value in available_required if value is not None)
    if coverage < policy.minimum_component_coverage:
        reasons["component_coverage"] = "P7_CONFIDENCE_COMPONENT_COVERAGE_INSUFFICIENT"
    return components, overall, missing, reasons, coverage

def _calibrated_records(
    candidate: CandidateFeatureRecord,
    score: dict[str, Any],
    model: dict[str, Any],
    report: dict[str, Any],
    policy: ConfidencePolicy,
) -> tuple[dict[str, Any], dict[str, Any]]:
    calibrator = _validate_evidence(model, report)
    raw = float(score["raw_ltr_score"])
    calibrated_value = float(calibrator["slope"]) * raw + float(calibrator["intercept"])
    components, overall, missing, reasons, coverage = _confidence_values(candidate, report, policy)
    calibration = {
        "candidate_id": candidate.candidate_id, "comparison_group_id": candidate.comparison_group_id,
        "raw_ltr_score": raw, "calibrated_ltr_score": calibrated_value, "calibration_status": "CALIBRATED",
        "calibration_method": "FROZEN_AFFINE_UTILITY_SCALE", "calibration_version": model["model_hash"],
        "target_id": model["target_id"], "lineage_id": candidate.lineage_id,
    }
    confidence = {
        "candidate_id": candidate.candidate_id, "comparison_group_id": candidate.comparison_group_id,
        "calibration_evidence_stage": components["calibration_evidence"],
        "fold_stability_stage": components["fold_stability"],
        "data_quality_stage": components["data_quality"], "ood_stage": components["ood"],
        "overall_confidence": overall,
        "confidence_status": (
            "CALIBRATED" if overall is not None and not missing
            else "PARTIALLY_CALIBRATED" if overall is not None
            else "UNAVAILABLE"
        ),
        "confidence_policy_version": policy.policy_version,
        "aggregation_method": "MIN_AVAILABLE_REQUIRED_COMPONENTS_WITH_COVERAGE_GATE",
        "required_components": list(policy.required_components),
        "component_coverage": coverage,
        "missing_components": missing,
        "component_reason_codes": reasons,
        "lineage_id": candidate.lineage_id,
    }
    return calibration, confidence


def calibrate_and_confidence(
    candidate_records: tuple[dict[str, Any], ...], score_records: tuple[dict[str, Any], ...],
    model_records: tuple[dict[str, Any], ...], reference_records: tuple[dict[str, Any], ...],
    qualification_reports: tuple[dict[str, Any], ...], policy: ConfidencePolicy,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = sorted((CandidateFeatureRecord.model_validate(row) for row in candidate_records),
                        key=lambda row: (row.comparison_group_id, row.candidate_id))
    scores = _by_candidate(score_records, "score")
    model, report = _resolved_evidence(model_records, reference_records, qualification_reports)
    calibrated: list[dict[str, Any]] = []
    confidence: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate.comparison_group_id, candidate.candidate_id)
        score = scores.get(key)
        if score is None:
            fail("P7_LTR_RUNTIME_CANDIDATE_RECONCILIATION_FAILED", f"missing score {key}")
        if score["score_status"] != "SCORED" or model is None or report is None:
            calibrated.append(_calibration_unavailable(candidate, score))
            confidence.append(_confidence_unavailable(candidate, policy))
            continue
        calibration_row, confidence_row = _calibrated_records(candidate, score, model, report, policy)
        calibrated.append(calibration_row)
        confidence.append(confidence_row)
    return calibrated, confidence


def _calibration_unavailable(candidate: CandidateFeatureRecord, score: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id, "comparison_group_id": candidate.comparison_group_id,
        "raw_ltr_score": score.get("raw_ltr_score"), "calibrated_ltr_score": None,
        "calibration_status": "UNAVAILABLE", "calibration_method": None, "calibration_version": None,
        "target_id": None, "lineage_id": candidate.lineage_id,
    }


def _confidence_unavailable(candidate: CandidateFeatureRecord, policy: ConfidencePolicy) -> dict[str, Any]:
    components: dict[str, float | None] = {
        "calibration_evidence": None,
        "fold_stability": None,
        "data_quality": candidate.data_quality_score,
        "ood": None if candidate.ood_score is None else 1.0 - candidate.ood_score,
    }
    missing = sorted(name for name in policy.required_components if components.get(name) is None)
    available = [components[name] for name in policy.required_components if components.get(name) is not None]
    coverage = len(available) / len(policy.required_components)
    reasons = {
        name: (
            "P7_CONFIDENCE_MODEL_EVIDENCE_UNAVAILABLE"
            if name in {"calibration_evidence", "fold_stability"}
            else f"P7_CONFIDENCE_COMPONENT_{name.upper()}_UNAVAILABLE"
        )
        for name in missing
    }
    if coverage < policy.minimum_component_coverage:
        reasons["component_coverage"] = "P7_CONFIDENCE_COMPONENT_COVERAGE_INSUFFICIENT"
    return {
        "candidate_id": candidate.candidate_id, "comparison_group_id": candidate.comparison_group_id,
        "calibration_evidence_stage": components["calibration_evidence"],
        "fold_stability_stage": components["fold_stability"],
        "data_quality_stage": components["data_quality"], "ood_stage": components["ood"],
        "overall_confidence": None, "confidence_status": "UNAVAILABLE",
        "confidence_policy_version": policy.policy_version,
        "aggregation_method": "MIN_AVAILABLE_REQUIRED_COMPONENTS_WITH_COVERAGE_GATE",
        "required_components": list(policy.required_components),
        "component_coverage": coverage,
        "missing_components": missing,
        "component_reason_codes": reasons,
        "lineage_id": candidate.lineage_id,
    }
