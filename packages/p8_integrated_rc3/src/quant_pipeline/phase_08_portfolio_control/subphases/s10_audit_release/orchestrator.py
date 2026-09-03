from __future__ import annotations
from .independent_auditor import run_independent_audit
from .models_common import ArtifactRef, content_sha256
from .models_handoff import P9HandoffRequest
from .models_orchestration import AuditReleaseRequest, AuditReleaseResult
from .models_qualification import QualificationRequest
from .p9_handoff_builder import build_p9_handoff
from .qualification_gate import run_qualification_gate

def run_audit_release(request: AuditReleaseRequest) -> AuditReleaseResult:
    audit = run_independent_audit(request.stateful_evidence)
    qualification = run_qualification_gate(QualificationRequest(
        context=request.stateful_evidence.context, terminal_state=request.terminal_state,
        audit_report=audit, robustness=request.robustness, statistical=request.statistical))
    template = request.p9_request_template
    audit_hash = content_sha256(audit)
    audit_ref = ArtifactRef(
        artifact_id=f"p8_audit_{audit_hash[:20]}", content_sha256=audit_hash,
        schema_version="1.0.0", contract_version="1.0.0",
        producer_phase="P8", producer_module="P8.S10.M01",
    )
    sources = tuple(ref for ref in template.source_artifacts if ref.producer_module != "P8.S10.M01") + (audit_ref,)
    handoff_request = P9HandoffRequest(context=template.context, qualification=qualification,
        evaluation_commitment=template.evaluation_commitment, all_candidate_ids=template.all_candidate_ids,
        evidence_records=template.evidence_records, lineage_records=template.lineage_records,
        audit_report_ref=audit_ref, runtime_evidence_ref=template.runtime_evidence_ref,
        source_artifacts=sources, full_evidence=template.full_evidence)
    handoff = build_p9_handoff(handoff_request)
    return AuditReleaseResult(audit_report=audit, qualification=qualification, p9_handoff=handoff)
