from __future__ import annotations
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance import RuntimeEvidenceBundle
from quant_pipeline.phase_08_portfolio_control.subphases.s09_runtime_assurance.models_common import content_sha256 as s9_hash
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_common import ArtifactRef
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_handoff import P9HandoffRequest

RUNTIME_SCHEMA_VERSION = "1.0.0"
RUNTIME_CONTRACT_VERSION = "1.0.0"

def runtime_evidence_to_s10_ref(bundle: RuntimeEvidenceBundle) -> ArtifactRef:
    digest=s9_hash(bundle)
    return ArtifactRef(artifact_id=f"p8_s9_runtime_evidence_{digest[:20]}",content_sha256=digest,
        schema_version=RUNTIME_SCHEMA_VERSION,contract_version=RUNTIME_CONTRACT_VERSION,
        producer_phase="P8",producer_module="P8.S9.M05")

def attach_runtime_evidence(template: P9HandoffRequest, ref: ArtifactRef) -> P9HandoffRequest:
    sources=tuple(x for x in template.source_artifacts if x.artifact_id != ref.artifact_id)+(ref,)
    return P9HandoffRequest(context=template.context,qualification=template.qualification,
        evaluation_commitment=template.evaluation_commitment,all_candidate_ids=template.all_candidate_ids,
        evidence_records=template.evidence_records,lineage_records=template.lineage_records,
        audit_report_ref=template.audit_report_ref,runtime_evidence_ref=ref,source_artifacts=sources)
