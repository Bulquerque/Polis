from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..closure import ClosurePointers, build_cycle_closure_manifest
from ..errors import BoundaryValidationError
from ..identity import stable_id
from ..contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    ExecutionStatus,
    ModuleTraceEntry,
    RuntimeFoundationContext,
    RuntimeIssue,
    content_hash,
)
from ..kernel import CapabilityExecution
from .models import ArtifactWriteRequest
from .ports import JsonArtifactRepositoryPort, ModuleBindingPort, ModuleExecutorPort


@dataclass(frozen=True, slots=True)
class ModulePipelineCapability:
    capability_id: str
    module_ids: tuple[str, ...]
    binding: ModuleBindingPort
    executor: ModuleExecutorPort
    repository: JsonArtifactRepositoryPort

    async def validate(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
    ) -> tuple[RuntimeIssue, ...]:
        return await self.binding.validate(self.module_ids, request, foundation, {})

    async def execute(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> CapabilityExecution:
        available = dict(artifacts)
        produced: dict[str, ArtifactPointer] = {}
        traces: list[ModuleTraceEntry] = []
        issues: list[RuntimeIssue] = []
        for module_id in self.module_ids:
            invocation = await self.binding.build(module_id, request, foundation, available)
            result = await self.executor.execute(module_id, invocation)
            input_material = [content_hash(value) for value in invocation.inputs.values()]
            if invocation.config:
                input_material.append(content_hash(invocation.config))
            input_hashes = tuple(sorted(input_material))
            output_hashes: list[str] = []
            for artifact_name, payload in result.outputs.items():
                pointer = await self.repository.write_json(
                    ArtifactWriteRequest(
                        artifact_name=artifact_name,
                        payload=payload,
                        producer_module_id=module_id,
                        schema_id=str(payload.get("schema_id") or f"p3.runtime.{artifact_name}.v1"),
                        schema_version="1.0.0",
                        lineage_id=str(payload["lineage_id"]) if payload.get("lineage_id") else None,
                    )
                )
                prior = available.get(artifact_name)
                if prior is not None and prior != pointer:
                    raise BoundaryValidationError(
                        f"{module_id} attempted to replace current-cycle artifact {artifact_name}"
                    )
                produced[artifact_name] = pointer
                available[artifact_name] = pointer
                output_hashes.append(pointer.content_hash)
            traces.append(
                ModuleTraceEntry(
                    cycle_id=request.cycle_id,
                    module_id=module_id,
                    input_hashes=input_hashes,
                    output_hashes=tuple(sorted(output_hashes)),
                    as_of_time=request.as_of_time,
                    status=(
                        ExecutionStatus.DEGRADED
                        if result.issues
                        else ExecutionStatus.READY
                    ),
                )
            )
            issues.extend(result.issues)
        return CapabilityExecution(
            artifacts=produced,
            module_trace=tuple(traces),
            issues=tuple(issues),
            status=ExecutionStatus.DEGRADED if issues else ExecutionStatus.READY,
        )


@dataclass(frozen=True, slots=True)
class ClosurePipelineCapability(ModulePipelineCapability):
    """S25-S26 pipeline plus canonical reference-based cycle-to-state closure."""

    required_closure_artifacts: tuple[str, ...] = (
        "validated_next_person_state_panel",
        "next_belief_state_panel",
        "next_memory_state",
        "next_social_graph",
        "next_cycle_endogenous_stimulus_queue",
        "belief_outcome_commitment_log",
        "tool_call_audit_panel",
        "cycle_state_snapshot_out",
    )

    async def execute(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> CapabilityExecution:
        execution = await ModulePipelineCapability.execute(self, request, foundation, artifacts)
        all_artifacts = dict(artifacts)
        all_artifacts.update(execution.artifacts)
        missing = [name for name in self.required_closure_artifacts if name not in all_artifacts]
        if missing:
            raise BoundaryValidationError(
                "society closure cannot be built; missing artifacts: " + ", ".join(missing)
            )
        pointers = ClosurePointers(
            next_person_state=all_artifacts["validated_next_person_state_panel"],
            next_belief_state=all_artifacts["next_belief_state_panel"],
            next_memory_state=all_artifacts["next_memory_state"],
            next_social_graph=all_artifacts["next_social_graph"],
            next_cycle_stimulus_queue=all_artifacts["next_cycle_endogenous_stimulus_queue"],
            belief_commitment_log=all_artifacts["belief_outcome_commitment_log"],
            tool_audit=all_artifacts["tool_call_audit_panel"],
            cycle_audit=all_artifacts["cycle_state_snapshot_out"],
        )
        closure = build_cycle_closure_manifest(
            foundation_manifest=foundation.manifest,
            foundation_manifest_ref=request.foundation_manifest_ref,
            source_cycle_id=request.cycle_id,
            target_cycle_id=self._target_cycle_id(request.cycle_id),
            pointers=pointers,
            status=execution.status,
            issues=execution.issues,
        )
        return CapabilityExecution(
            artifacts=execution.artifacts,
            module_trace=execution.module_trace,
            tool_audits=execution.tool_audits,
            closure_manifest=closure,
            status=execution.status,
            issues=execution.issues,
        )

    @staticmethod
    def _target_cycle_id(source: str) -> str:
        prefix, separator, suffix = source.rpartition("-")
        if separator and suffix.isdigit():
            return f"{prefix}-{int(suffix) + 1:0{len(suffix)}d}"
        return stable_id("next-cycle", source)


@dataclass(frozen=True, slots=True)
class ProductPipelineCapability(ModulePipelineCapability):
    p4_artifact_names: tuple[str, ...] = (
        "social_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "phase4_social_handoff_manifest",
    )
    p9_artifact_names: tuple[str, ...] = (
        "p9_evaluation_evidence_bundle",
        "p9_context_learning_handoff_manifest",
    )
    variable_evolution_artifact_name: str = "variable_evolution_input_manifest"

    async def execute(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> CapabilityExecution:
        execution = await ModulePipelineCapability.execute(self, request, foundation, artifacts)
        all_artifacts = dict(artifacts)
        all_artifacts.update(execution.artifacts)
        required = (*self.p4_artifact_names, *self.p9_artifact_names, self.variable_evolution_artifact_name)
        missing = [name for name in required if name not in all_artifacts]
        if missing:
            raise BoundaryValidationError(
                "PRODUCTS did not materialize required external outputs: " + ", ".join(missing)
            )
        return CapabilityExecution(
            artifacts=execution.artifacts,
            module_trace=execution.module_trace,
            tool_audits=execution.tool_audits,
            p4_outputs=tuple(all_artifacts[name] for name in self.p4_artifact_names),
            p9_outputs=tuple(all_artifacts[name] for name in self.p9_artifact_names),
            variable_evolution_output=all_artifacts[self.variable_evolution_artifact_name],
            status=execution.status,
            issues=execution.issues,
        )
