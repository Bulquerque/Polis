from __future__ import annotations
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import run_runtime_assurance
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release import AuditReleaseRequest, run_audit_release
from .bridge import attach_runtime_evidence, runtime_evidence_to_s10_ref
from .models import Agent5IntegratedRequest, Agent5IntegratedResult

def run_agent5_integrated(request: Agent5IntegratedRequest) -> Agent5IntegratedResult:
    runtime_result=run_runtime_assurance(request.runtime_request)
    runtime_ref=runtime_evidence_to_s10_ref(runtime_result.evidence_bundle)
    audit=request.audit_request
    updated_template=attach_runtime_evidence(audit.p9_request_template,runtime_ref)
    updated_audit=AuditReleaseRequest(stateful_evidence=audit.stateful_evidence,terminal_state=audit.terminal_state,
        robustness=audit.robustness,statistical=audit.statistical,p9_request_template=updated_template)
    audit_result=run_audit_release(updated_audit)
    return Agent5IntegratedResult(runtime_result=runtime_result,runtime_evidence_ref=runtime_ref,
        audit_release_result=audit_result)
