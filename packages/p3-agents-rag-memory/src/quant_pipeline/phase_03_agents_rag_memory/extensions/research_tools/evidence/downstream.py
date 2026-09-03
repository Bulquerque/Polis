"""Supplemental, consumer-ready P4 and P9 handoffs."""
from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import Phase3RunSnapshot
from quant_pipeline.phase_03_agents_rag_memory.s31_models import ModelKnowledgeCutoffReport

from ..runtime.models import (
    ConsumerCompatibilityStatus,
    DownstreamHandoffManifest,
    P9LearningEvidenceBundle,
    P9LearningEvidenceRecord,
    ResearchProcessPanel,
    ResearchProcessRecord,
    ResearchToolExecutionTracePanel,
    S40Lineage,
)


def _commitment_refs(panel: object) -> dict[str, tuple[str, ...]]:
    result: dict[str, set[str]] = {}
    records = panel.get("records", ()) if isinstance(panel, Mapping) else getattr(panel, "records", ())
    for raw in records if isinstance(records, (tuple, list)) else ():
        item = raw if isinstance(raw, Mapping) else getattr(raw, "model_dump", lambda **_: {})()
        tx = item.get("cognition_transaction_id")
        commitment = item.get("commitment_id") or item.get("belief_proposal_id")
        if isinstance(tx, str) and isinstance(commitment, str):
            result.setdefault(tx, set()).add(commitment)
    return {key: tuple(sorted(value)) for key, value in result.items()}


def build_p4_handoff(
    *,
    process_panel: ResearchProcessPanel,
    compatibility_status: ConsumerCompatibilityStatus = ConsumerCompatibilityStatus.PRODUCER_READY_CONSUMER_NOT_YET_WIRED,
    required_consumer_changes: tuple[str, ...] | None = None,
) -> tuple[DownstreamHandoffManifest, dict[str, object]]:
    lineage = _lineage(
        "P3.S40.M06",
        "research_process_panel",
        process_panel.panel_hash,
        "p3.s40.p4.supplemental.handoff.v2",
    )
    changes = required_consumer_changes
    if changes is None:
        changes = (
            "P4 must add an optional input binding for research_process_panel",
            "P4 must keep existing social handoffs backward compatible",
        )
    body = {
        "handoff_id": f"p4-research-process:{process_panel.panel_hash[:20]}",
        "consumer_phase": "P4",
        "compatibility_status": compatibility_status,
        "artifact_ids": ("research_process_panel",),
        "schema_refs": ("extensions/research_tools/schemas/runtime/research_process_panel.schema.json",),
        "content_hashes": (process_panel.panel_hash,),
        "required_consumer_changes": changes,
        "lineage": lineage,
    }
    manifest = DownstreamHandoffManifest(**body, manifest_hash=content_hash(body))
    return manifest, _consumer_report(manifest, "P4", feedback_timing=None)


def build_p9_learning_evidence(
    *,
    process_panel: ResearchProcessPanel,
    trace_panel: ResearchToolExecutionTracePanel,
    phase3_snapshot: Phase3RunSnapshot,
    model_knowledge_cutoff: ModelKnowledgeCutoffReport,
    belief_commitment_panel: object,
) -> tuple[P9LearningEvidenceBundle, DownstreamHandoffManifest, dict[str, object]]:
    if model_knowledge_cutoff.known_training_cutoff is not None:
        if model_knowledge_cutoff.known_training_cutoff > phase3_snapshot.as_of.date():
            raise ValueError("model knowledge cutoff exceeds the P3 decision date")
    commitments = _commitment_refs(belief_commitment_panel)
    missing = tuple(
        sorted(
            process.cognition_transaction_id
            for process in process_panel.records
            if not commitments.get(process.cognition_transaction_id)
        )
    )
    if missing:
        raise ValueError(f"P9 evidence requires prior belief commitments: {missing}")
    traces = _trace_hashes(trace_panel)
    cutoff_hash = content_hash(model_knowledge_cutoff.model_dump(mode="json"))
    records = tuple(
        record
        for process in process_panel.records
        for record in _learning_records(
            process,
            phase3_snapshot,
            commitments,
            traces,
            cutoff_hash,
            model_knowledge_cutoff.known_training_cutoff,
        )
    )
    lineage = _bundle_lineage(process_panel, trace_panel, cutoff_hash)
    bundle_body = {
        "records": records,
        "model_knowledge_cutoff_hash": cutoff_hash,
        "known_training_cutoff": model_knowledge_cutoff.known_training_cutoff,
        "eligible_feedback_cycle": "N_PLUS_1_ONLY",
        "lineage": lineage,
    }
    bundle = P9LearningEvidenceBundle(**bundle_body, bundle_hash=content_hash(bundle_body))
    handoff = _p9_handoff(bundle, lineage)
    return bundle, handoff, _consumer_report(handoff, "P9", feedback_timing="N_PLUS_1_ONLY")


def _learning_records(process, snapshot, commitments, trace_hashes, cutoff_hash, known_cutoff):
    result = []
    trace_hash = trace_hashes.get(process.cognition_transaction_id, content_hash([]))
    per_call_cost = process.cost_units / max(process.visible_tool_call_count, 1)
    for key, requested, executed in zip(
        process.operation_keys,
        process.requested_modes,
        process.executed_modes,
        strict=True,
    ):
        tool_id, operation_id = key.split("/", 1)
        body = {
            "learning_evidence_id": f"p9-tool-learning:{content_hash([process.process_id, key])[:20]}",
            "run_id": snapshot.run_id,
            "cycle_id": snapshot.cycle_id,
            "cognition_transaction_id": process.cognition_transaction_id,
            "person_id": process.person_id,
            "tool_id": tool_id,
            "operation_id": operation_id,
            "requested_mode": requested,
            "executed_mode": executed,
            "cost_units": per_call_cost,
            "evidence_coverage": process.evidence_coverage,
            "source_quality_mean": process.source_quality_mean,
            "belief_commitment_refs": commitments[process.cognition_transaction_id],
            "evidence_refs": process.evidence_refs,
            "result_hash": process.process_hash,
            "trace_hash": trace_hash,
            "model_knowledge_cutoff_hash": cutoff_hash,
            "known_training_cutoff": known_cutoff,
            "eligible_feedback_cycle": "N_PLUS_1_ONLY",
        }
        result.append(P9LearningEvidenceRecord(**body))
    return tuple(result)


def _trace_hashes(panel):
    grouped: dict[str, list[str]] = {}
    for trace in panel.records:
        grouped.setdefault(trace.cognition_transaction_id, []).append(trace.event_hash)
    return {key: content_hash(sorted(values)) for key, values in grouped.items()}


def _lineage(module_id, artifact_id, digest, transformation):
    return S40Lineage(
        lineage_id=f"{module_id}:{digest[:20]}",
        producer_module_id=module_id,
        source_artifact_ids=(artifact_id,),
        source_hashes={artifact_id: digest},
        transformation_ids=(transformation,),
    )


def _bundle_lineage(process_panel, trace_panel, cutoff_hash):
    hashes = {
        "research_process_panel": process_panel.panel_hash,
        "research_tool_execution_trace_panel": trace_panel.panel_hash,
        "model_knowledge_cutoff_report": cutoff_hash,
    }
    return S40Lineage(
        lineage_id=f"P3.S40.M07:{content_hash(hashes)[:20]}",
        producer_module_id="P3.S40.M07",
        source_artifact_ids=tuple(hashes),
        source_hashes=hashes,
        transformation_ids=("p3.s40.p9.learning.evidence.v2",),
    )


def _p9_handoff(bundle, lineage):
    body = {
        "handoff_id": f"p9-research-learning:{bundle.bundle_hash[:20]}",
        "consumer_phase": "P9",
        # Global RC4.1 explicitly forbids a direct P3 -> P9 edge.  The
        # evidence remains local and immutable until governance introduces an
        # approved intermediary or amends the global connection contract.
        "compatibility_status": ConsumerCompatibilityStatus.DEFERRED_BY_GOVERNANCE,
        "artifact_ids": ("p9_research_tool_learning_evidence",),
        "schema_refs": ("extensions/research_tools/schemas/runtime/p9_learning_evidence_bundle.schema.json",),
        "content_hashes": (bundle.bundle_hash,),
        "required_consumer_changes": (
            "No direct P3-to-P9 transfer is permitted under global RC4.1",
            "P0 must approve an intermediary or a global contract amendment before transfer",
            "P9 feedback must remain N+1 only",
        ),
        "lineage": lineage,
    }
    return DownstreamHandoffManifest(**body, manifest_hash=content_hash(body))


def _consumer_report(manifest, phase, feedback_timing):
    report = {
        "status": manifest.compatibility_status.value,
        "consumer_phase": phase,
        "producer_ready": True,
        "consumer_wired": manifest.compatibility_status is ConsumerCompatibilityStatus.CONSUMER_COMPATIBLE,
        "governance_deferred": manifest.compatibility_status is ConsumerCompatibilityStatus.DEFERRED_BY_GOVERNANCE,
        "breaking_change": False,
        "content_hash": manifest.manifest_hash,
    }
    if feedback_timing:
        report["feedback_timing"] = feedback_timing
    return report
