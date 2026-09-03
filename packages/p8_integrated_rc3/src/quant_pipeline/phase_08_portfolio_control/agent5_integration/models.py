from __future__ import annotations
from pydantic import BaseModel, ConfigDict, model_validator
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeAssuranceRequest, RuntimeAssuranceResult
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release import AuditReleaseRequest, AuditReleaseResult
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_common import ArtifactRef

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

class Agent5IntegratedRequest(StrictModel):
    runtime_request: RuntimeAssuranceRequest
    audit_request: AuditReleaseRequest

    @model_validator(mode="after")
    def contexts_match(self) -> "Agent5IntegratedRequest":
        runtime = self.runtime_request.context
        audit = self.audit_request.stateful_evidence.context
        pairs = ((runtime.run_id,audit.run_id,"run_id"),(runtime.cycle_id,audit.cycle_id,"cycle_id"),
                 (runtime.trace_id,audit.trace_id,"trace_id"),(runtime.decision_time,audit.decision_time,"decision_time"))
        for left,right,name in pairs:
            if left != right:
                raise ValueError(f"runtime and audit {name} must match")
        if runtime.observed_at > audit.audit_time:
            raise ValueError("runtime observed_at cannot follow audit_time")
        return self

class Agent5IntegratedResult(StrictModel):
    runtime_result: RuntimeAssuranceResult
    runtime_evidence_ref: ArtifactRef
    audit_release_result: AuditReleaseResult
