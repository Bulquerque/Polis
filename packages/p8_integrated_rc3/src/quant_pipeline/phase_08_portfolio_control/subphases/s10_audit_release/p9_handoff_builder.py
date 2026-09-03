from __future__ import annotations
import hashlib
from .errors import ContractIntegrityError
from .models_handoff import P9EvaluationHandoff, P9HandoffRequest

def _handoff_id(request: P9HandoffRequest) -> str:
    raw = f"{request.context.run_id}|{request.context.cycle_id}|{request.qualification.qualification_id}"
    return "p9h_" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def _validate_candidate_coverage(request: P9HandoffRequest) -> None:
    expected = set(request.all_candidate_ids)
    evidence_ids = {item.candidate_id for item in request.evidence_records}
    lineage_ids = {item.candidate_id for item in request.lineage_records}
    if len(request.all_candidate_ids) != len(expected):
        raise ContractIntegrityError("all_candidate_ids contains duplicates")
    if evidence_ids != expected:
        missing = sorted(expected-evidence_ids)
        extra = sorted(evidence_ids-expected)
        raise ContractIntegrityError(f"candidate evidence mismatch missing={missing} extra={extra}")
    if lineage_ids != expected or len(request.lineage_records) != len(lineage_ids):
        raise ContractIntegrityError("candidate lineage must cover each candidate exactly once")

def build_p9_handoff(request: P9HandoffRequest) -> P9EvaluationHandoff:
    _validate_candidate_coverage(request)
    return P9EvaluationHandoff(handoff_id=_handoff_id(request), context=request.context,
        qualification=request.qualification, evaluation_commitment=request.evaluation_commitment,
        all_candidate_ids=request.all_candidate_ids, evidence_records=request.evidence_records,
        lineage_records=request.lineage_records, audit_report_ref=request.audit_report_ref,
        runtime_evidence_ref=request.runtime_evidence_ref, source_artifacts=request.source_artifacts,
        full_evidence=request.full_evidence, production_promotion_allowed=False)
