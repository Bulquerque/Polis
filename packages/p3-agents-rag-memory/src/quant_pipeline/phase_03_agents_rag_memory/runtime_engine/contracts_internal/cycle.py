from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from ...contracts.cycle import BudgetLimits, CapabilityFlags

from .base import (
    ArtifactPointer,
    ExecutionMode,
    ExecutionStatus,
    LineageRecord,
    NonEmptyStr,
    NonNegativeInt,
    RuntimeIssue,
    Sha256,
    StrictBoundaryModel,
    content_hash,
    utc,
)
from .foundation import FoundationRuntimeManifest


class ReplayState(StrictBoundaryModel):
    schema_id: Literal["p3.integration.replay_state.v1"] = "p3.integration.replay_state.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    as_of_time: datetime
    person_state: ArtifactPointer
    belief_state: ArtifactPointer
    memory_state: ArtifactPointer
    social_graph: ArtifactPointer
    pending_stimuli: ArtifactPointer
    belief_commitments: ArtifactPointer
    resource_manifest_ref: ArtifactPointer
    audit_refs: tuple[ArtifactPointer, ...] = ()
    status: ExecutionStatus
    lineage: LineageRecord
    state_hash: Sha256

    @field_validator("as_of_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def state_hash_consistent(self) -> "ReplayState":
        payload = self.model_dump(mode="json", exclude={"state_hash"})
        if content_hash(payload) != self.state_hash:
            raise ValueError("replay state_hash is invalid")
        expected_names = {
            "person_state": "validated_next_person_state_panel",
            "belief_state": "next_belief_state_panel",
            "memory_state": "next_memory_state",
            "social_graph": "next_social_graph",
            "pending_stimuli": "next_cycle_endogenous_stimulus_queue",
            "belief_commitments": "belief_outcome_commitment_log",
            "resource_manifest_ref": "p3_foundation_runtime_manifest",
        }
        for field_name, expected_name in expected_names.items():
            pointer = getattr(self, field_name)
            if pointer.artifact_name != expected_name:
                raise ValueError(
                    f"ReplayState {field_name} must reference {expected_name}"
                )
            if pointer.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
                raise ValueError(f"ReplayState {field_name} is not consumable")
        if len({pointer.artifact_id for pointer in self.audit_refs}) != len(self.audit_refs):
            raise ValueError("ReplayState audit_refs must be unique")
        return self


class CycleKernelRequest(StrictBoundaryModel):
    schema_id: Literal["p3.integration.cycle_kernel_request.v1"] = (
        "p3.integration.cycle_kernel_request.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    mode: ExecutionMode
    as_of_time: datetime
    logical_time: datetime
    foundation_manifest: FoundationRuntimeManifest
    foundation_manifest_ref: ArtifactPointer
    prior_state: ReplayState | None
    stimulus_ref: ArtifactPointer
    schedule_context_ref: ArtifactPointer | None = None
    seed: NonNegativeInt
    capability_flags: CapabilityFlags
    budget: BudgetLimits
    replay_bundle: ArtifactPointer | None = None

    @property
    def emit_p4_outputs(self) -> bool:
        return self.capability_flags.emit_p4_outputs

    @property
    def emit_p9_outputs(self) -> bool:
        return self.capability_flags.emit_p9_outputs

    @field_validator("as_of_time", "logical_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def mode_policy(self) -> "CycleKernelRequest":
        if self.run_id != self.foundation_manifest.run_id:
            raise ValueError("request run_id must match foundation manifest")
        if self.snapshot_id != self.foundation_manifest.snapshot_id:
            raise ValueError("request snapshot_id must match foundation manifest")
        if self.as_of_time != self.foundation_manifest.as_of_time:
            raise ValueError("request as_of_time must match foundation manifest cutoff")
        if self.foundation_manifest_ref.artifact_id != self.foundation_manifest.artifact_id:
            raise ValueError("foundation_manifest_ref artifact_id must match manifest")
        if self.foundation_manifest_ref.schema_id != self.foundation_manifest.schema_id:
            raise ValueError("foundation_manifest_ref schema_id must match manifest")
        if self.foundation_manifest_ref.schema_version != self.foundation_manifest.schema_version:
            raise ValueError("foundation_manifest_ref schema_version must match manifest")
        if self.foundation_manifest_ref.content_hash != self.foundation_manifest.content_hash:
            raise ValueError("foundation_manifest_ref content_hash must match manifest")
        if self.prior_state is not None:
            if self.prior_state.run_id != self.run_id or self.prior_state.snapshot_id != self.snapshot_id:
                raise ValueError("prior_state identity must match the cycle request")
            if self.prior_state.as_of_time > self.as_of_time:
                raise ValueError("prior_state cannot be newer than the cycle cutoff")
            if self.prior_state.cycle_id == self.cycle_id:
                raise ValueError("prior_state must belong to a different cycle")
        if self.mode is ExecutionMode.REPLAY and self.replay_bundle is None:
            raise ValueError("REPLAY requires replay_bundle")
        if self.replay_bundle is not None and self.replay_bundle.status in {
            ExecutionStatus.BLOCKED,
            ExecutionStatus.FAILED,
        }:
            raise ValueError("replay_bundle is not consumable")
        if self.stimulus_ref.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
            raise ValueError("stimulus_ref is not consumable")
        if self.logical_time > self.as_of_time and self.mode is not ExecutionMode.WARMUP_REPLAY:
            raise ValueError("logical_time cannot exceed the run cutoff")
        if self.mode in {ExecutionMode.WARMUP_REPLAY, ExecutionMode.REPLAY, ExecutionMode.DRY_RUN}:
            if self.emit_p4_outputs or self.emit_p9_outputs or self.capability_flags.emit_variable_evolution:
                raise ValueError(f"{self.mode} cannot emit external outputs")
        if self.mode is ExecutionMode.LIVE and not (
            self.emit_p4_outputs
            and self.emit_p9_outputs
            and self.capability_flags.emit_variable_evolution
        ):
            raise ValueError("LIVE must explicitly enable P4, P9 and variable-evolution outputs")
        return self


class ModuleTraceEntry(StrictBoundaryModel):
    cycle_id: NonEmptyStr
    module_id: Annotated[str, Field(pattern=r"^P3\.S(?:1[7-9]|2[0-9]|3[0-1])\.M\d{2}$")]
    input_hashes: tuple[Sha256, ...]
    output_hashes: tuple[Sha256, ...]
    as_of_time: datetime
    status: ExecutionStatus

    @field_validator("as_of_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)


class ToolAuditEntry(StrictBoundaryModel):
    tool_call_id: NonEmptyStr
    tool_id: NonEmptyStr
    person_id: NonEmptyStr
    available_at: datetime
    status: Annotated[str, Field(pattern=r"^(SUCCEEDED|FAILED|REJECTED)$")]
    request_hash: Sha256
    result_hash: Sha256 | None = None

    @field_validator("available_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def result_hash_policy(self) -> "ToolAuditEntry":
        if self.status == "SUCCEEDED" and self.result_hash is None:
            raise ValueError("SUCCEEDED tool audit requires result_hash")
        if self.status == "REJECTED" and self.result_hash is not None:
            raise ValueError("REJECTED tool audit cannot contain result_hash")
        return self


class P3CycleClosureManifest(StrictBoundaryModel):
    artifact_name: Literal["p3_cycle_closure_manifest"] = "p3_cycle_closure_manifest"
    schema_id: Literal["p3.integration.cycle_closure_manifest.v1"] = (
        "p3.integration.cycle_closure_manifest.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    source_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    as_of_time: datetime
    lineage: LineageRecord
    foundation_manifest_ref: ArtifactPointer
    next_person_state: ArtifactPointer
    next_belief_state: ArtifactPointer
    next_memory_state: ArtifactPointer
    next_social_graph: ArtifactPointer
    next_cycle_stimulus_queue: ArtifactPointer
    belief_commitment_log: ArtifactPointer
    tool_audit: ArtifactPointer
    cycle_audit: ArtifactPointer
    status: ExecutionStatus
    issues: tuple[RuntimeIssue, ...] = ()
    content_hash: Sha256

    @field_validator("as_of_time")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def closure_consistent(self) -> "P3CycleClosureManifest":
        if self.source_cycle_id == self.target_cycle_id:
            raise ValueError("closure target_cycle_id must differ from source_cycle_id")
        expected_names = {
            "foundation_manifest_ref": "p3_foundation_runtime_manifest",
            "next_person_state": "validated_next_person_state_panel",
            "next_belief_state": "next_belief_state_panel",
            "next_memory_state": "next_memory_state",
            "next_social_graph": "next_social_graph",
            "next_cycle_stimulus_queue": "next_cycle_endogenous_stimulus_queue",
            "belief_commitment_log": "belief_outcome_commitment_log",
            "tool_audit": "tool_call_audit_panel",
            "cycle_audit": "cycle_state_snapshot_out",
        }
        for field_name, expected_name in expected_names.items():
            pointer = getattr(self, field_name)
            if pointer.artifact_name != expected_name:
                raise ValueError(f"closure {field_name} must reference {expected_name}")
            if pointer.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
                raise ValueError(f"closure {field_name} is not consumable")
        if self.status is ExecutionStatus.READY and self.issues:
            raise ValueError("READY closure cannot contain runtime issues")
        if self.status is ExecutionStatus.DEGRADED and not self.issues:
            raise ValueError("DEGRADED closure requires at least one runtime issue")
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        if content_hash(payload) != self.content_hash:
            raise ValueError("cycle closure content_hash is invalid")
        return self


class CycleKernelResult(StrictBoundaryModel):
    schema_id: Literal["p3.integration.cycle_kernel_result.v1"] = (
        "p3.integration.cycle_kernel_result.v1"
    )
    schema_version: Literal["1.0.0"] = "1.0.0"
    request_id: NonEmptyStr
    mode: ExecutionMode
    status: ExecutionStatus
    closure_manifest: P3CycleClosureManifest | None
    module_trace: tuple[ModuleTraceEntry, ...]
    tool_audits: tuple[ToolAuditEntry, ...] = ()
    p4_outputs: tuple[ArtifactPointer, ...] = ()
    p9_outputs: tuple[ArtifactPointer, ...] = ()
    variable_evolution_output: ArtifactPointer | None = None
    issues: tuple[RuntimeIssue, ...] = ()

    @model_validator(mode="after")
    def result_policy(self) -> "CycleKernelResult":
        if self.mode is ExecutionMode.DRY_RUN:
            if self.closure_manifest is not None or self.p4_outputs or self.p9_outputs or self.variable_evolution_output is not None:
                raise ValueError("DRY_RUN cannot emit runtime artifacts")
        else:
            if self.closure_manifest is None:
                raise ValueError("executed cycle requires closure_manifest")
        if self.mode is not ExecutionMode.LIVE and (self.p4_outputs or self.p9_outputs or self.variable_evolution_output is not None):
            raise ValueError("only LIVE may emit P4/P9 outputs")
        if self.mode is ExecutionMode.LIVE:
            if len(self.p4_outputs) != 6 or len(self.p9_outputs) != 2 or self.variable_evolution_output is None:
                raise ValueError("LIVE requires six P4 outputs, two P9 outputs and one variable-evolution output")
        return self
