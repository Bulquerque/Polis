from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import (
    CONTRACT_PACK_ID,
    CONTRACT_PACK_VERSION,
    ArtifactPointer,
    ArtifactStatus,
    ContractModel,
    CycleStatus,
    ExecutionMode,
    LineageRecord,
    NonEmptyStr,
    RunIdentity,
    Sha256,
    StateSource,
    content_hash,
    utc,
)


class CapabilityFlags(ContractModel):
    allow_live_providers: bool = False
    allow_tool_execution: bool = False
    emit_p4_outputs: bool = False
    emit_p9_outputs: bool = False
    emit_variable_evolution: bool = False
    require_frozen_provider_responses: bool = True


class BudgetLimits(ContractModel):
    max_llm_calls: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=0, ge=0)
    max_retrieval_calls: int = Field(default=0, ge=0)
    max_total_tokens: int = Field(default=0, ge=0)


class CycleKernelRequest(ContractModel):
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    request_id: NonEmptyStr
    identity: RunIdentity
    cycle_id: NonEmptyStr
    mode: ExecutionMode
    logical_time: datetime
    foundation_manifest_ref: ArtifactPointer
    prior_state_ref: ArtifactPointer | None = None
    stimulus_ref: ArtifactPointer
    schedule_context_ref: ArtifactPointer | None = None
    seed: int = Field(ge=0)
    capability_flags: CapabilityFlags
    budget: BudgetLimits

    @field_validator("logical_time")
    @classmethod
    def aware_logical_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def mode_policy(self) -> "CycleKernelRequest":
        flags = self.capability_flags
        if self.foundation_manifest_ref.available_at is not None and (
            self.foundation_manifest_ref.available_at > self.identity.as_of_time
        ):
            raise ValueError("foundation manifest is newer than the cycle cutoff")
        if self.mode in {ExecutionMode.WARMUP_REPLAY, ExecutionMode.REPLAY}:
            if flags.allow_live_providers:
                raise ValueError(f"{self.mode.value} cannot use live providers")
            if flags.emit_p4_outputs or flags.emit_p9_outputs or flags.emit_variable_evolution:
                raise ValueError(f"{self.mode.value} cannot emit external outputs")
        if self.mode is ExecutionMode.DRY_RUN:
            if flags.allow_live_providers or flags.allow_tool_execution:
                raise ValueError("DRY_RUN cannot execute providers or tools")
            if flags.emit_p4_outputs or flags.emit_p9_outputs or flags.emit_variable_evolution:
                raise ValueError("DRY_RUN cannot emit external outputs")
        if self.mode is ExecutionMode.LIVE and not (
            flags.emit_p4_outputs and flags.emit_p9_outputs and flags.emit_variable_evolution
        ):
            raise ValueError("LIVE must explicitly enable all external output families")
        return self


class P4Outputs(ContractModel):
    social_feature_panel_ref: ArtifactPointer
    evidence_tag_panel_ref: ArtifactPointer
    agent_disagreement_panel_ref: ArtifactPointer
    context_memory_feature_panel_ref: ArtifactPointer
    hypothesis_registry_ref: ArtifactPointer
    phase4_social_handoff_manifest_ref: ArtifactPointer


class P9Outputs(ContractModel):
    evaluation_evidence_bundle_ref: ArtifactPointer
    context_learning_handoff_manifest_ref: ArtifactPointer


class CrossPhaseOutputs(ContractModel):
    p4: P4Outputs | None = None
    p9: P9Outputs | None = None
    variable_evolution_input_manifest_ref: ArtifactPointer | None = None


class P3CycleClosureManifest(ContractModel):
    artifact_name: Literal["p3_cycle_closure_manifest"] = "p3_cycle_closure_manifest"
    schema_id: Literal["p3.integration.cycle_closure_manifest.v2"] = (
        "p3.integration.cycle_closure_manifest.v2"
    )
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    identity: RunIdentity
    source_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    completed_at: datetime
    foundation_manifest_ref: ArtifactPointer
    next_person_state_ref: ArtifactPointer
    next_belief_state_ref: ArtifactPointer
    next_memory_state_ref: ArtifactPointer
    next_social_graph_ref: ArtifactPointer
    next_endogenous_queue_ref: ArtifactPointer
    belief_commitments_ref: ArtifactPointer
    tool_audit_ref: ArtifactPointer
    cycle_snapshot_ref: ArtifactPointer
    status: ArtifactStatus
    issues: tuple[NonEmptyStr, ...] = ()
    lineage: LineageRecord
    content_hash: Sha256

    @field_validator("completed_at")
    @classmethod
    def aware_completed_at(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def closure_policy(self) -> "P3CycleClosureManifest":
        if self.source_cycle_id == self.target_cycle_id:
            raise ValueError("closure target cycle must differ from source cycle")
        if self.status is ArtifactStatus.READY and self.issues:
            raise ValueError("READY closure cannot contain issues")
        return self


class CycleKernelResult(ContractModel):
    contract_pack_id: Literal["P3_INTEGRATION_CONTRACT_PACK_V2"] = CONTRACT_PACK_ID
    contract_pack_version: Literal["2.0.0"] = CONTRACT_PACK_VERSION
    request_id: NonEmptyStr
    identity: RunIdentity
    cycle_id: NonEmptyStr
    mode: ExecutionMode
    status: CycleStatus
    closure_manifest_ref: ArtifactPointer | None = None
    next_state_ref: ArtifactPointer | None = None
    checkpoint_ref: ArtifactPointer | None = None
    audit_summary_ref: ArtifactPointer | None = None
    module_trace_ref: ArtifactPointer | None = None
    cross_phase_outputs: CrossPhaseOutputs = CrossPhaseOutputs()
    issues: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def result_policy(self) -> "CycleKernelResult":
        if self.mode is ExecutionMode.DRY_RUN:
            if any((self.closure_manifest_ref, self.next_state_ref, self.checkpoint_ref)):
                raise ValueError("DRY_RUN cannot emit state artifacts")
            if self.status not in {CycleStatus.DRY_RUN_VALIDATED, CycleStatus.BLOCKED, CycleStatus.FAILED}:
                raise ValueError("DRY_RUN must report a dry-run status")
        else:
            if self.closure_manifest_ref is None:
                raise ValueError("executed cycle requires a closure manifest")
            if self.next_state_ref is None:
                raise ValueError("executed cycle requires a ReplayState reference")
            if self.next_state_ref.artifact_name != "replay_state":
                raise ValueError("next_state_ref must reference replay_state")
            if self.next_state_ref.artifact_id == self.closure_manifest_ref.artifact_id:
                raise ValueError("next_state_ref cannot point to the closure manifest")
        if self.mode is not ExecutionMode.LIVE and self.cross_phase_outputs != CrossPhaseOutputs():
            raise ValueError("only LIVE may emit cross-phase outputs")
        if self.mode is ExecutionMode.LIVE:
            if self.cross_phase_outputs.p4 is None or self.cross_phase_outputs.p9 is None:
                raise ValueError("LIVE requires P4 and P9 outputs")
            if self.cross_phase_outputs.variable_evolution_input_manifest_ref is None:
                raise ValueError("LIVE requires variable evolution output")
        return self


class ReplayState(ContractModel):
    artifact_name: Literal["replay_state"] = "replay_state"
    schema_id: Literal["p3.integration.replay_state.v2"] = "p3.integration.replay_state.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    identity: RunIdentity
    source_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    source: StateSource
    person_state_ref: ArtifactPointer
    belief_state_ref: ArtifactPointer
    memory_state_ref: ArtifactPointer
    social_graph_ref: ArtifactPointer
    pending_stimuli_ref: ArtifactPointer
    belief_commitments_ref: ArtifactPointer
    foundation_manifest_ref: ArtifactPointer
    audit_refs: tuple[ArtifactPointer, ...] = ()
    state_hash: Sha256
    lineage: LineageRecord

    @model_validator(mode="after")
    def replay_state_consistent(self) -> "ReplayState":
        if self.source_cycle_id == self.target_cycle_id:
            raise ValueError("ReplayState target cycle must differ from source cycle")
        if self.source is StateSource.GENESIS and self.source_cycle_id != "GENESIS":
            raise ValueError("GENESIS ReplayState must use source_cycle_id='GENESIS'")
        expected = {
            "person_state_ref": "validated_next_person_state_panel",
            "belief_state_ref": "next_belief_state_panel",
            "memory_state_ref": "next_memory_state",
            "social_graph_ref": "next_social_graph",
            "pending_stimuli_ref": "next_cycle_endogenous_stimulus_queue",
            "belief_commitments_ref": "belief_outcome_commitment_log",
            "foundation_manifest_ref": "p3_foundation_runtime_manifest",
        }
        for field_name, artifact_name in expected.items():
            pointer = getattr(self, field_name)
            if pointer.artifact_name != artifact_name:
                raise ValueError(f"{field_name} must reference {artifact_name}")
            if pointer.status in {ArtifactStatus.BLOCKED, ArtifactStatus.FAILED}:
                raise ValueError(f"{field_name} is not consumable")
        payload = self.model_dump(mode="json", exclude={"state_hash"})
        if content_hash(payload) != self.state_hash:
            raise ValueError("ReplayState state_hash is invalid")
        return self
