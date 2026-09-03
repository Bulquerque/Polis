"""Deterministic company result construction."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pydantic import JsonValue

from .evidence import evidence_for_records
from .models import CompanyMode, CompanyOperationResult, OperationCoverage, OutcomeStatus, hashed_payload


def build_company_result(
    *, operation_id: str, requested_mode: CompanyMode, executed_mode: CompanyMode, method_id: str,
    metrics: Mapping[str, JsonValue], records: Sequence[Mapping[str, JsonValue]], records_requested: int,
    records_rejected_future: int, missing_requirements: Sequence[str] = (),
    outcome_status: OutcomeStatus | None = None, downgrade_reason: str | None = None,
    reason_codes: Sequence[str] = (), diagnostics: Sequence[str] = (), cost_units: int = 1,
) -> CompanyOperationResult:
    normalized = tuple(dict(item) for item in records)
    evidence = evidence_for_records(normalized) if normalized else ()
    missing = tuple(sorted(set(missing_requirements)))
    score = min(1.0, len(normalized) / max(records_requested, 1))
    coverage = OperationCoverage(
        score=score, records_requested=records_requested, records_used=len(normalized),
        records_rejected_future=records_rejected_future, missing_requirements=missing,
    )
    if outcome_status is None:
        if not normalized and not metrics:
            outcome_status = OutcomeStatus.EMPTY_VALID
        elif missing or downgrade_reason:
            outcome_status = OutcomeStatus.DEGRADED
        else:
            outcome_status = OutcomeStatus.PASS
    latest = max((item.available_at for item in evidence), default=None)
    payload = {
        "operation_id": operation_id, "requested_mode": requested_mode, "executed_mode": executed_mode,
        "outcome_status": outcome_status, "method_id": method_id, "method_version": "1.0.0",
        "downgrade_reason": downgrade_reason, "metrics": dict(metrics), "records": normalized,
        "evidence_refs": evidence, "coverage": coverage, "latest_available_at": latest,
        "reason_codes": tuple(reason_codes), "diagnostics": tuple(diagnostics), "cost_units": cost_units,
    }
    return CompanyOperationResult(**payload, result_hash=hashed_payload(payload))
