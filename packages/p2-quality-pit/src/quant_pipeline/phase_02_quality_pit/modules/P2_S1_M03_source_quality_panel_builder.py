from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s1_core import group_by_source, match_rows, rows_or_empty

_REQUIRED_INPUTS = ["validated_phase1_handoff_bundle", "raw_readability_report", "ingestion_error_report"]
_POLICY_VERSION = "p2.source_quality.v1"


def _readability_status(source_rows: list[dict], readability_rows: list[dict]) -> str:
    statuses: list[str] = []
    for source_row in source_rows:
        matched = match_rows(source_row, readability_rows)
        for row in matched:
            value = row.get("readability_status") or row.get("status")
            if value:
                statuses.append(str(value).strip().lower())
        fallback = source_row.get("readability_status")
        if fallback:
            statuses.append(str(fallback).strip().lower())
    if not statuses:
        return "unknown"
    if any(status in {"unreadable", "failed", "fail", "error", "block"} for status in statuses):
        return "unreadable"
    if any(status in {"warning", "warn", "partial", "degraded"} for status in statuses):
        return "warning"
    if all(status in {"readable", "pass", "ok"} for status in statuses):
        return "readable"
    return statuses[0]


def _quality_for_source(source_rows: list[dict], readability_rows: list[dict], error_rows: list[dict]) -> tuple[float, str, list[str], bool, bool]:
    score = 1.0
    reasons: list[str] = []
    readability = _readability_status(source_rows, readability_rows)

    relevant_errors = [row for source_row in source_rows for row in match_rows(source_row, error_rows)]
    blocking_error = any(bool(row.get("is_blocking")) for row in relevant_errors)
    error_flag = any(bool(row.get("error_flag") or row.get("is_blocking")) for row in relevant_errors)
    warning_flag = any(bool(row.get("warning_flag")) for row in source_rows)

    if readability == "unreadable":
        score = 0.0
        reasons.append("UNREADABLE_ARTIFACT")
    elif readability == "warning":
        score -= 0.15
        warning_flag = True
        reasons.append("READABILITY_WARNING")
    elif readability == "unknown":
        score -= 0.15
        warning_flag = True
        reasons.append("READABILITY_UNKNOWN")

    if blocking_error:
        score = 0.0
        reasons.append("BLOCKING_INGESTION_ERROR")
    else:
        non_blocking_errors = [row for row in relevant_errors if row.get("error_flag") and not row.get("is_blocking")]
        if non_blocking_errors:
            score -= 0.25
            error_flag = True
            reasons.append("NON_BLOCKING_INGESTION_ERROR")

    if any(bool(row.get("warning_flag")) for row in source_rows):
        score -= 0.10
        warning_flag = True
        reasons.append("SOURCE_WARNING_FLAG")

    if any(bool(row.get("truncation_flag")) or row.get("pagination_complete") is False for row in source_rows):
        score -= 0.25
        warning_flag = True
        reasons.append("CAPTURE_INCOMPLETE")

    score = max(0.0, min(1.0, round(score, 6)))
    if score == 0.0:
        status = "BLOCK"
    elif score < 0.70:
        status = "DEGRADED"
    elif score < 0.90:
        status = "WARN"
    else:
        status = "PASS"
    return score, status, sorted(set(reasons)), error_flag, warning_flag


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    require_inputs(inputs, _REQUIRED_INPUTS)
    handoff_rows = records(inputs["validated_phase1_handoff_bundle"], _REQUIRED_INPUTS[0])
    if not handoff_rows:
        raise ContractValidationError("source_quality_score_present violation: validated handoff is empty")

    readability_rows = rows_or_empty(inputs["raw_readability_report"], _REQUIRED_INPUTS[1])
    error_rows = rows_or_empty(inputs["ingestion_error_report"], _REQUIRED_INPUTS[2])
    grouped = group_by_source(handoff_rows)
    if not grouped:
        raise ContractValidationError("critical_source_flags_present violation: source_id is required")

    panel: list[dict] = []
    for source_id in sorted(grouped):
        source_rows = grouped[source_id]
        score, status, reasons, error_flag, warning_flag = _quality_for_source(
            source_rows,
            readability_rows,
            error_rows,
        )
        representative = source_rows[0]
        declared_available_at = representative.get("declared_available_at") or representative.get("available_at")
        if not declared_available_at:
            raise ContractValidationError(
                f"source_quality_score_present violation: declared_available_at missing for source {source_id}"
            )
        lineage_id = representative.get("lineage_id")
        if not lineage_id:
            raise ContractValidationError(f"critical_source_flags_present violation: lineage_id missing for {source_id}")

        panel.append(
            {
                "source_id": source_id,
                "source_name": representative.get("source_name") or source_id,
                "source_type": representative.get("source_type") or "unknown",
                "quality_score": score,
                "quality_status": status,
                "quality_reasons": reasons,
                "quality_policy_version": _POLICY_VERSION,
                "readability_status": _readability_status(source_rows, readability_rows),
                "error_flag": error_flag,
                "warning_flag": warning_flag,
                "declared_available_at": declared_available_at,
                "critical": bool(representative.get("critical", False)),
                "artifact_count": len(source_rows),
                "lineage_id": lineage_id,
            }
        )

    no_forbidden_rows(panel)
    if any("quality_score" not in row or "critical" not in row for row in panel):
        raise ContractValidationError("source_quality_score_present/critical_source_flags_present violation")

    return {
        "module_id": "P2.S1.M03",
        "module_name": "source_quality_panel_builder",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S1",
        "contract": "P2_S1_M03_source_quality_panel_builder.yaml",
        "required_inputs": _REQUIRED_INPUTS,
        "outputs": {"source_quality_panel": artifact("source-quality-panel", panel, config)},
    }
