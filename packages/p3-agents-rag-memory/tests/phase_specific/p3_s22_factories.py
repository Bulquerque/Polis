from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_hashing import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus,
    BeliefValueType,
    DirectionalBeliefPayload,
    EvidenceRef,
    ExecutionMode,
    LineageRecord,
    Phase3RunSnapshot,
    PropositionDefinition,
    PropositionRegistryConfig,
    RawToolResultRecord,
    RetrievalEvidenceMap,
    StructuredBeliefProposalPanel,
    StructuredBeliefProposalRecord,
    ToolExecutionStatus,
    ToolResultValidationStatus,
    ValidatedToolResultPanel,
    ValidatedToolResultRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s22_models import (
    BeliefPolicyConfig,
    CurrentBeliefStatePanel,
    CurrentBeliefStateRecord,
    GraphEvidenceMap,
    GraphEvidenceRecord,
    RagEvidenceRecord,
    RagIndexArtifact,
)

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def lineage(module_id: str) -> LineageRecord:
    return LineageRecord(lineage_id=f"lineage-{module_id}", producer_module_id=module_id)


def snapshot(*, as_of: datetime = NOW) -> Phase3RunSnapshot:
    return Phase3RunSnapshot(
        run_id="run-1", cycle_id="cycle-1", snapshot_id="snapshot-1",
        as_of=as_of, execution_mode=ExecutionMode.LIVE, configuration_hash="cfg-hash",
    )


def registry() -> PropositionRegistryConfig:
    return PropositionRegistryConfig(
        registry_version="1.0.0",
        propositions=(
            PropositionDefinition(
                proposition_id="directional_outlook",
                value_type=BeliefValueType.DIRECTIONAL_SCORE,
                allowed_horizons=("1d","5d","21d"),
                direction_mapping={"DOWN":-1.0,"FLAT":0.0,"UP":1.0},
            ),
            PropositionDefinition(
                proposition_id="volatility_outlook",
                value_type=BeliefValueType.VOLATILITY_LEVEL,
                allowed_horizons=("1d","5d","21d"),
            ),
        ),
    )


def proposal_panel(*, evidence=("ev-1",), opposing=(), generated_at: datetime = NOW, proposition="directional_outlook", horizon="1d", score: float = 0.7, direction: str = "UP") -> StructuredBeliefProposalPanel:
    payload = DirectionalBeliefPayload(value_type=BeliefValueType.DIRECTIONAL_SCORE, direction=direction, score=score)
    return StructuredBeliefProposalPanel(
        records=(StructuredBeliefProposalRecord(
            belief_proposal_id="proposal-1", cognition_transaction_id="tx-1", person_id="person-1",
            underlying_id="ABC", proposition_id=proposition, horizon=horizon, payload=payload,
            strength=0.8, confidence=0.75, uncertainty=0.25,
            supporting_evidence_refs=tuple(evidence), opposing_evidence_refs=tuple(opposing),
            generated_at=generated_at, as_of=generated_at,
        ),),
        lineage=lineage("P3.S21.M06"),
    )


def current_state(*, score: float = 0.2) -> CurrentBeliefStatePanel:
    return CurrentBeliefStatePanel(
        records=(CurrentBeliefStateRecord(
            belief_state_id="belief-state-1", person_id="person-1", underlying_id="ABC",
            proposition_id="directional_outlook", horizon="1d",
            payload=DirectionalBeliefPayload(value_type=BeliefValueType.DIRECTIONAL_SCORE, direction="UP", score=score),
            confidence=0.6, uncertainty=0.4, evidence_refs=("ev-old",), updated_at=NOW-timedelta(days=1), state_version=2,
        ),),
        lineage=lineage("P3.S11.M03"),
    )


def empty_state() -> CurrentBeliefStatePanel:
    return CurrentBeliefStatePanel(status=ArtifactStatus.EMPTY_VALID, records=(), lineage=lineage("P3.S11.M03"), reason_code="GENESIS")


def retrieval() -> RetrievalEvidenceMap:
    return RetrievalEvidenceMap(
        records=(EvidenceRef(evidence_id="ev-1", source_id="source-1", available_at=NOW, content_hash="hash-ev-1", source_quality=0.9),),
        lineage=lineage("P3.S20.M05"),
    )


def graph() -> GraphEvidenceMap:
    return GraphEvidenceMap(status=ArtifactStatus.EMPTY_VALID, records=(), lineage=lineage("P3.S13.M02"), reason_code="NO_GRAPH_EVIDENCE")


def rag() -> RagIndexArtifact:
    return RagIndexArtifact(schema_version="p3.s22.v1", artifact_id="rag-1", created_at=NOW, as_of=NOW, content_hash="rag-hash", records=(), lineage=lineage("P3.S12.M02"))


def tool_results() -> ValidatedToolResultPanel:
    return ValidatedToolResultPanel(status=ArtifactStatus.EMPTY_VALID, records=(), lineage=lineage("P3.S21.M04"), reason_code="NO_TOOL")


def valid_tool_results() -> ValidatedToolResultPanel:
    raw = RawToolResultRecord(
        tool_call_request_id="request-1", cognition_transaction_id="tx-1", execution_id="exec-1",
        person_id="person-1", tool_id="market_lookup", operation_id="latest_snapshot", provider_id="mcp-demo",
        status=ToolExecutionStatus.SUCCEEDED, started_at=NOW, finished_at=NOW, available_at=NOW,
        latency_ms=1.0, cost_units=0.01, canonical_payload={"price":101.5}, response_hash=content_hash({"price":101.5}), evidence_refs=("tool-ev-1",), result_schema={"type":"object"},
    )
    return ValidatedToolResultPanel(
        records=(ValidatedToolResultRecord(raw_result=raw, validation_status=ToolResultValidationStatus.VALID, validated_payload={"price":101.5}),),
        lineage=lineage("P3.S21.M04"),
    )


def policy(**updates: object) -> BeliefPolicyConfig:
    return BeliefPolicyConfig().model_copy(update=updates)
