"""Build S7 scoring, confidence, group and decomposition records."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .common import artifact_records, candidate_index


def _confidence_values(record: Mapping[str, Any]) -> tuple[float | None, float | None, str, str]:
    overall = record.get("overall_confidence")
    ood_stage = record.get("ood_stage")
    return (
        float(overall) if overall is not None else None,
        float(ood_stage) if ood_stage is not None else None,
        str(record.get("confidence_status", "UNAVAILABLE")),
        str(record.get("confidence_policy_version", "UNAVAILABLE")),
    )


def _hybrid_record(row: Mapping[str, Any], base: Mapping[str, Any], *, cycle_id: str, decision_time: Any):
    from ..finalization.boundary.inputs import HybridScoreRecord

    score = row.get("hybrid_score")
    liquidity = base.get("cost_liquidity", {}).get("liquidity_score")
    return HybridScoreRecord(
        cycle_id=cycle_id, decision_time=decision_time, candidate_id=str(row["candidate_id"]),
        comparison_group_id=str(row["comparison_group_id"]),
        hybrid_score=float(score) if score is not None else None,
        robust_score=float(score) if score is not None else None,
        execution_quality=float(liquidity) if liquidity is not None else None,
        complexity_score=None, model_id=str(row.get("model_hash") or "interpretable-baseline-v2.2"),
        model_promotion_status="PROMOTED" if row.get("model_hash") else "CHAMPION",
        model_compatibility_status="COMPATIBLE" if score is not None else "UNAVAILABLE",
        score_semantics_version="hybrid-v2.2", lineage_id=str(row.get("lineage_id", base.get("lineage_id"))),
    )


def _confidence_record(
    row: Mapping[str, Any], evidence: Mapping[str, Any], base: Mapping[str, Any],
    *, cycle_id: str, decision_time: Any,
):
    from ..finalization.boundary.inputs import ConfidenceRecord

    confidence, ood_stage, status, version = _confidence_values(evidence)
    severity = "UNAVAILABLE" if ood_stage is None else ("NONE" if ood_stage >= 0.8 else "MODERATE")
    return ConfidenceRecord(
        cycle_id=cycle_id, decision_time=decision_time, candidate_id=str(row["candidate_id"]),
        score_confidence=confidence, score_interval_lower=None, score_interval_upper=None,
        model_disagreement=None, calibration_status=status, calibration_version=version,
        ood_severity=severity, lineage_id=str(row.get("lineage_id", base.get("lineage_id"))),
    )


def _group_record(row: Mapping[str, Any], base: Mapping[str, Any], *, cycle_id: str, decision_time: Any):
    from ..finalization.boundary.inputs import ComparisonGroupRecord

    return ComparisonGroupRecord(
        cycle_id=cycle_id, decision_time=decision_time, candidate_id=str(row["candidate_id"]),
        comparison_group_id=str(row["comparison_group_id"]), underlying_id=str(row["underlying_id"]),
        horizon=str(row["horizon"]), objective_family=str(row["objective_family"]),
        risk_bucket=str(row["capital_at_risk_bucket"]), lineage_id=str(base.get("lineage_id")),
    )


def build_scoring_records(
    score_rows: list[dict[str, Any]], confidence_rows: list[dict[str, Any]],
    eligible: Mapping[str, dict[str, Any]], groups: Mapping[str, dict[str, Any]],
    *, cycle_id: str, decision_time: Any,
) -> tuple[list[Any], list[Any], list[Any]]:
    confidence_index = candidate_index(confidence_rows, "ltr_score_confidence_panel")
    hybrid: list[Any] = []
    confidence: list[Any] = []
    group_records: list[Any] = []
    for row in score_rows:
        candidate_id = str(row["candidate_id"])
        base = eligible[candidate_id]
        hybrid.append(_hybrid_record(row, base, cycle_id=cycle_id, decision_time=decision_time))
        confidence.append(_confidence_record(
            row, confidence_index[candidate_id], base, cycle_id=cycle_id, decision_time=decision_time
        ))
        group_records.append(_group_record(groups[candidate_id], base, cycle_id=cycle_id, decision_time=decision_time))
    return hybrid, confidence, group_records


def decomposition_records(learning: Mapping[str, Any], *, cycle_id: str, decision_time: Any) -> list[dict[str, Any]]:
    rows = artifact_records(learning["hybrid_score_decomposition_panel"], "hybrid_score_decomposition_panel")
    result: list[dict[str, Any]] = []
    decision_wire = decision_time.isoformat().replace("+00:00", "Z")
    for row in rows:
        base = {
            "cycle_id": cycle_id, "decision_time": decision_wire,
            "candidate_id": str(row["candidate_id"]),
            "lineage_id": str(row.get("lineage_id", f"decomposition:{row['candidate_id']}")),
        }
        result.append({**base, "head": "interpretable", "contribution": float(row.get("interpretable_contribution") or 0.0)})
        if row.get("ltr_contribution") is not None:
            result.append({**base, "head": "ltr", "contribution": float(row["ltr_contribution"])})
    return result


def blocked_records(rows: list[dict[str, Any]], *, cycle_id: str, decision_time: Any) -> list[Any]:
    from ..finalization.boundary.inputs import PreFinalBlockedRecord

    return [
        PreFinalBlockedRecord(
            cycle_id=cycle_id, decision_time=decision_time, candidate_id=str(row["candidate_id"]),
            reason_codes=tuple(row.get("reason_codes", ("P7_UPSTREAM_ELIGIBILITY_BLOCK",))),
            evidence_ids=tuple(row.get("evidence", ())),
            lineage_id=str(row.get("lineage_id", f"blocked:{row['candidate_id']}")),
        )
        for row in rows
    ]
