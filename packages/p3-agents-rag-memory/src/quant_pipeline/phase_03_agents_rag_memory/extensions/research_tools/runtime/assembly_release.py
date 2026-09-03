"""Release-gate orchestration for P3.S40.M08."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from ..qualification.release import build_release_gate
from .assembly_support import lineage, parse
from .models import (
    DownstreamHandoffManifest, HandlerRegistryCompletenessReport,
    OperationModeQualificationMatrix, QualificationEvidenceManifest,
    ResearchToolLeakageReport, S21RuntimePreflightReport,
)


async def execute_m08(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    completeness = parse(HandlerRegistryCompletenessReport, inputs["handler_registry_completeness_report"])
    preflight = parse(S21RuntimePreflightReport, inputs["s21_runtime_preflight_report"])
    qualification = parse(OperationModeQualificationMatrix, inputs["operation_mode_qualification_matrix"])
    leakage = parse(ResearchToolLeakageReport, inputs["research_tool_leakage_report"])
    qualification_evidence = parse(QualificationEvidenceManifest, inputs["qualification_evidence_manifest"])
    p4_manifest = parse(DownstreamHandoffManifest, inputs["phase4_research_process_handoff_manifest"])
    p9_manifest = parse(DownstreamHandoffManifest, inputs["p9_research_tool_learning_handoff_manifest"])
    p4_report = _mapping(inputs.get("p4_research_handoff_compatibility_report"))
    p9_report = _mapping(inputs.get("p9_consumer_compatibility_report"))
    evidence_integrity = _release_evidence_integrity(
        completeness=completeness,
        preflight=preflight,
        qualification=qualification,
        leakage=leakage,
        qualification_evidence=qualification_evidence,
        p4_manifest=p4_manifest,
        p4_report=p4_report,
        p9_manifest=p9_manifest,
        p9_report=p9_report,
    )
    gate, issues = build_release_gate(
        completeness=completeness,
        preflight=preflight,
        qualification=qualification,
        leakage=leakage,
        p4_report=p4_report,
        p9_report=p9_report,
        contract_report=_mapping(inputs.get("contract_test_report")),
        schema_report=_mapping(inputs.get("schema_test_report")),
        code_quality_report=_mapping(inputs.get("code_quality_report")),
        hash_integrity_report=_mapping(inputs.get("hash_integrity_report")),
        rollback_report=_mapping(inputs.get("rollback_report")),
        evidence_integrity_report=evidence_integrity,
        lineage=lineage("P3.S40.M08", inputs, tuple(inputs)),
        technical_qualification=True,
    )
    package = {
        "gate_hash": gate.gate_hash,
        "blocking_issue_panel_hash": issues.panel_hash,
        "qualification_evidence_manifest_hash": qualification_evidence.manifest_hash,
        "p4_handoff_manifest_hash": p4_manifest.manifest_hash,
        "p9_handoff_manifest_hash": p9_manifest.manifest_hash,
        "release_evidence_integrity_hash": str(evidence_integrity["content_hash"]),
        "promotion_authority": "P0_ONLY",
    }
    package["content_hash"] = content_hash(package)
    return {
        "research_tool_extension_release_gate": gate.model_dump(mode="json"),
        "research_tool_extension_evidence_package": package,
        "research_tool_extension_blocking_issue_panel": issues.model_dump(mode="json"),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _release_evidence_integrity(
    *,
    completeness: HandlerRegistryCompletenessReport,
    preflight: S21RuntimePreflightReport,
    qualification: OperationModeQualificationMatrix,
    leakage: ResearchToolLeakageReport,
    qualification_evidence: QualificationEvidenceManifest,
    p4_manifest: DownstreamHandoffManifest,
    p4_report: Mapping[str, object],
    p9_manifest: DownstreamHandoffManifest,
    p9_report: Mapping[str, object],
) -> dict[str, object]:
    expected_evidence = {
        "operation_mode_qualification_matrix": qualification.matrix_hash,
        "research_tool_leakage_report": leakage.report_hash,
        "handler_registry_completeness_report": completeness.report_hash,
        "s21_runtime_preflight_report": preflight.report_hash,
    }
    if len(qualification_evidence.artifact_ids) != len(qualification_evidence.artifact_hashes):
        actual_evidence: dict[str, str] = {}
        reasons: list[str] = ["P3RT-RELEASE-QUALIFICATION-EVIDENCE-LENGTH-MISMATCH"]
    else:
        actual_evidence = dict(zip(
            qualification_evidence.artifact_ids,
            qualification_evidence.artifact_hashes,
            strict=True,
        ))
        reasons = []
    if actual_evidence != expected_evidence:
        reasons.append("P3RT-RELEASE-QUALIFICATION-EVIDENCE-MISMATCH")
    reasons.extend(_handoff_reasons(p4_manifest, p4_report, "P4"))
    reasons.extend(_handoff_reasons(p9_manifest, p9_report, "P9"))
    if p9_report.get("feedback_timing") != "N_PLUS_1_ONLY":
        reasons.append("P3RT-RELEASE-P9-FEEDBACK-TIMING-INVALID")
    body: dict[str, object] = {
        "status": "FAIL" if reasons else "PASS",
        "reason_codes": tuple(dict.fromkeys(reasons)),
    }
    body["content_hash"] = content_hash(body)
    return body


def _handoff_reasons(
    manifest: DownstreamHandoffManifest,
    report: Mapping[str, object],
    phase: str,
) -> list[str]:
    reasons: list[str] = []
    if manifest.consumer_phase != phase:
        reasons.append(f"P3RT-RELEASE-{phase}-MANIFEST-PHASE-MISMATCH")
    if report.get("status") != manifest.compatibility_status.value:
        reasons.append(f"P3RT-RELEASE-{phase}-COMPATIBILITY-MISMATCH")
    if report.get("content_hash") != manifest.manifest_hash:
        reasons.append(f"P3RT-RELEASE-{phase}-MANIFEST-HASH-MISMATCH")
    return reasons
