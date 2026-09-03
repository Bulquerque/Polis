"""Evidence, qualification, and downstream orchestration for P3.S40.M04-M07."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    Phase3RunSnapshot,
    RawToolResultPanel,
    RetrievalEvidenceMap,
    ToolCallAuditPanel,
    ValidatedToolResultPanel,
)
from quant_pipeline.phase_03_agents_rag_memory.s31_models import ModelKnowledgeCutoffReport

from ..evidence.downstream import build_p4_handoff, build_p9_learning_evidence
from ..evidence.overlay import build_tool_evidence_overlay
from ..evidence.process import build_research_process_panel
from ..qualification.matrix import (
    build_leakage_report,
    build_operation_mode_matrix,
    build_qualification_evidence_manifest,
)
from .assembly_support import expected_keys, family_reports, lineage, parse
from .models import (
    ConsumerCompatibilityStatus,
    HandlerRegistryCompletenessReport,
    RegistryStatus,
    ResearchProcessPanel,
    ResearchToolExecutionTracePanel,
    ResearchToolResultEnvelopePanel,
    S21RuntimePreflightReport,
)

_FAMILY_QUALIFICATION_INPUTS = (
    ("research.corpus.v1", "corpus_operation_mode_qualification"),
    ("market.derivatives.v1", "market_derivatives_operation_mode_qualification"),
    ("macro.research.v1", "macro_operation_mode_qualification"),
    ("company.research.v1", "company_operation_mode_qualification"),
    ("quant.diagnostics.v1", "quant_operation_mode_qualification"),
)


async def execute_m04(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    outputs = build_tool_evidence_overlay(
        raw_results=parse(RawToolResultPanel, inputs["raw_tool_result_panel"]),
        audit_panel=parse(ToolCallAuditPanel, inputs["tool_call_audit_panel"]),
        retrieval_evidence=parse(RetrievalEvidenceMap, inputs["retrieval_evidence_map"]),
        decision_time=parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"]).as_of,
    )
    return {name: value.model_dump(mode="json") for name, value in outputs.items()}


def _receipt_blocker(name: str, receipt: object) -> str | None:
    if not isinstance(receipt, Mapping):
        return f"P3RT-QUAL-{name.upper()}-RECEIPT-INVALID"
    status = receipt.get("status")
    if status is not None and str(status).upper() not in {"PASS", "READY", "VALID"}:
        return f"P3RT-QUAL-{name.upper()}-FAILED"
    total = receipt.get("tests_run", receipt.get("total", 0))
    passed = receipt.get("passed", 0)
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        return f"P3RT-QUAL-{name.upper()}-RECEIPT-MISSING"
    if not isinstance(passed, int) or isinstance(passed, bool) or passed != total:
        return f"P3RT-QUAL-{name.upper()}-FAILED"
    return None


async def execute_m05(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    source_lineage = lineage("P3.S40.M05", inputs, tuple(inputs))
    integration = inputs["integration_test_receipts"]
    leakage_receipt = inputs["leakage_test_receipts"]
    replay = inputs["replay_test_receipts"]
    completeness = parse(
        HandlerRegistryCompletenessReport,
        inputs["handler_registry_completeness_report"],
    )
    preflight = parse(S21RuntimePreflightReport, inputs["s21_runtime_preflight_report"])

    blockers: list[str] = []
    if completeness.status is RegistryStatus.FAILED:
        blockers.append("P3RT-HANDLER-REGISTRY-INCOMPLETE")
    if preflight.status is RegistryStatus.FAILED:
        blockers.append("P3RT-RUNTIME-S21-PREFLIGHT-FAILED")
    for name, receipt in (
        ("integration", integration),
        ("leakage", leakage_receipt),
        ("replay", replay),
    ):
        blocker = _receipt_blocker(name, receipt)
        if blocker:
            blockers.append(blocker)

    reports: list[object] = []
    for fallback_tool_id, input_name in _FAMILY_QUALIFICATION_INPUTS:
        reports.extend(family_reports({fallback_tool_id: inputs[input_name]}))

    matrix = build_operation_mode_matrix(
        family_reports=tuple(reports),
        integration_receipt=integration if isinstance(integration, Mapping) else {},
        leakage_receipt=leakage_receipt if isinstance(leakage_receipt, Mapping) else {},
        replay_receipt=replay if isinstance(replay, Mapping) else {},
        lineage=source_lineage,
        blocking_reason_codes=blockers,
    )
    leakage = build_leakage_report(
        leakage_receipt=leakage_receipt if isinstance(leakage_receipt, Mapping) else {},
        lineage=source_lineage,
    )
    evidence = build_qualification_evidence_manifest(
        artifact_ids=(
            "operation_mode_qualification_matrix",
            "research_tool_leakage_report",
            "handler_registry_completeness_report",
            "s21_runtime_preflight_report",
        ),
        artifact_hashes=(
            matrix.matrix_hash,
            leakage.report_hash,
            completeness.report_hash,
            preflight.report_hash,
        ),
        lineage=source_lineage,
    )
    return {
        "operation_mode_qualification_matrix": matrix.model_dump(mode="json"),
        "research_tool_leakage_report": leakage.model_dump(mode="json"),
        "qualification_evidence_manifest": evidence.model_dump(mode="json"),
    }


def _registered_modes(value: object) -> set[str]:
    if isinstance(value, Mapping):
        raw = value.get("modes", value.get("records", value.get("operation_modes", ())))
    else:
        raw = ()
    result: set[str] = set()
    for item in raw if isinstance(raw, (tuple, list)) else ():
        data = item if isinstance(item, Mapping) else getattr(item, "model_dump", lambda **_: {})()
        for field in ("mode_id", "research_mode", "name"):
            candidate = data.get(field)
            if isinstance(candidate, str) and candidate:
                result.add(candidate)
                break
    return result


async def execute_m06(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    panel = build_research_process_panel(
        validated_results=parse(ValidatedToolResultPanel, inputs["validated_tool_result_panel"]),
        audit_panel=parse(ToolCallAuditPanel, inputs["tool_call_audit_panel"]),
        envelopes=parse(ResearchToolResultEnvelopePanel, inputs["research_tool_result_envelope_panel"]),
        phase3_snapshot=parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"]),
        belief_panel=inputs["evidence_bound_belief_update_panel"],
    )
    declared_operations = expected_keys({
        "canonical_tool_operation_registry": inputs["canonical_tool_operation_registry"]
    }) or set()
    declared_modes = _registered_modes(inputs["research_mode_registry"])
    unknown_operations = tuple(sorted(
        key
        for record in panel.records
        for key in record.operation_keys
        if tuple(key.split("/", 1)) not in declared_operations
    ))
    unknown_modes = tuple(sorted({
        mode
        for record in panel.records
        for mode in (*record.requested_modes, *record.executed_modes)
        if mode not in declared_modes
    }))
    if unknown_operations or unknown_modes:
        changes = tuple(
            [f"unknown operation IDs: {','.join(unknown_operations)}"] if unknown_operations else []
        ) + tuple(
            [f"unknown research modes: {','.join(unknown_modes)}"] if unknown_modes else []
        )
        handoff, report = build_p4_handoff(
            process_panel=panel,
            compatibility_status=ConsumerCompatibilityStatus.INCOMPATIBLE,
            required_consumer_changes=changes,
        )
    else:
        handoff, report = build_p4_handoff(process_panel=panel)
    return {
        "research_process_panel": panel.model_dump(mode="json"),
        "phase4_research_process_handoff_manifest": handoff.model_dump(mode="json"),
        "p4_research_handoff_compatibility_report": report,
    }


async def execute_m07(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    del context
    bundle, handoff, report = build_p9_learning_evidence(
        process_panel=parse(ResearchProcessPanel, inputs["research_process_panel"]),
        trace_panel=parse(ResearchToolExecutionTracePanel, inputs["research_tool_execution_trace_panel"]),
        phase3_snapshot=parse(Phase3RunSnapshot, inputs["phase3_run_snapshot"]),
        model_knowledge_cutoff=parse(
            ModelKnowledgeCutoffReport,
            inputs["model_knowledge_cutoff_report"],
        ),
        belief_commitment_panel=inputs["belief_outcome_commitment_log"],
    )
    return {
        "p9_research_tool_learning_evidence": bundle.model_dump(mode="json"),
        "p9_research_tool_learning_handoff_manifest": handoff.model_dump(mode="json"),
        "p9_consumer_compatibility_report": report,
    }
