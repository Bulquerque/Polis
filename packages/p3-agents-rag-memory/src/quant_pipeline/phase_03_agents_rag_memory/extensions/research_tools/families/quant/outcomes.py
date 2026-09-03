"""Construction of deterministic quantitative operation results."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import JsonValue

from .evidence import evidence_for_records
from .models import OperationCoverage, OutcomeStatus, QuantMode, QuantOperationResult, hashed_payload


def build_quant_result(
    *,
    operation_id: str,
    requested_mode: QuantMode,
    executed_mode: QuantMode,
    method_id: str,
    metrics: Mapping[str, JsonValue],
    evidence_records: Sequence[Mapping[str, JsonValue]],
    observations_requested: int,
    observations_used: int,
    rejected_future: int,
    rejected_quality: int = 0,
    series: Sequence[Mapping[str, JsonValue]] = (),
    missing_requirements: Sequence[str] = (),
    outcome_status: OutcomeStatus | None = None,
    downgrade_reason: str | None = None,
    reason_codes: Sequence[str] = (),
    diagnostics: Sequence[str] = (),
) -> QuantOperationResult:
    evidence = evidence_for_records(evidence_records)
    missing = tuple(sorted(set(missing_requirements)))
    denominator = max(observations_requested, 1)
    score = max(0.0, min(1.0, observations_used / denominator))
    coverage = OperationCoverage(
        score=score,
        observations_requested=observations_requested,
        observations_used=observations_used,
        observations_rejected_future=rejected_future,
        observations_rejected_quality=rejected_quality,
        missing_requirements=missing,
    )
    if outcome_status is None:
        if observations_used == 0:
            outcome_status = OutcomeStatus.EMPTY_VALID
        elif missing or downgrade_reason or rejected_quality:
            outcome_status = OutcomeStatus.DEGRADED
        else:
            outcome_status = OutcomeStatus.PASS
    latest_available_at: datetime | None = None
    if evidence:
        latest_available_at = max(item.available_at for item in evidence)
    normalized_series = tuple(dict(item) for item in series)
    payload = {
        "operation_id": operation_id,
        "requested_mode": requested_mode,
        "executed_mode": executed_mode,
        "outcome_status": outcome_status,
        "method_id": method_id,
        "method_version": "1.0.0",
        "downgrade_reason": downgrade_reason,
        "metrics": dict(metrics),
        "series": normalized_series,
        "evidence_refs": evidence,
        "coverage": coverage,
        "latest_available_at": latest_available_at,
        "reason_codes": tuple(reason_codes),
        "diagnostics": tuple(diagnostics),
    }
    return QuantOperationResult(**payload, result_hash=hashed_payload(payload))
