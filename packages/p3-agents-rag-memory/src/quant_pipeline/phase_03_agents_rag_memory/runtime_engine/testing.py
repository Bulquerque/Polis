from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    ResolvedArtifact,
    RuntimeFoundationContext,
    RuntimeIssue,
)
from .kernel import CapabilityExecution


@dataclass(slots=True)
class InMemoryArtifactResolver:
    artifacts: Mapping[str, ResolvedArtifact]

    async def resolve(self, pointer: ArtifactPointer) -> ResolvedArtifact:
        artifact = self.artifacts[pointer.artifact_id]
        if artifact.pointer != pointer:
            raise ValueError(f"pointer mismatch for artifact {pointer.artifact_id}")
        return artifact


@dataclass(slots=True)
class RecordingCapability:
    """Deterministic capability test double with production-identical port semantics."""

    execution: CapabilityExecution
    validation_issues: tuple[RuntimeIssue, ...] = ()
    calls: list[str] = field(default_factory=list)

    async def validate(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
    ) -> tuple[RuntimeIssue, ...]:
        del foundation
        self.calls.append(f"validate:{request.mode}")
        return self.validation_issues

    async def execute(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> CapabilityExecution:
        del foundation, artifacts
        self.calls.append(f"execute:{request.mode}")
        return self.execution
