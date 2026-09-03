from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from ..contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    RuntimeFoundationContext,
    RuntimeIssue,
)
from .models import ArtifactWriteRequest, JsonPayload, ModuleExecutionResult, ModuleInvocation


@runtime_checkable
class JsonArtifactRepositoryPort(Protocol):
    async def read_json(self, pointer: ArtifactPointer) -> JsonPayload: ...

    async def write_json(self, request: ArtifactWriteRequest) -> ArtifactPointer: ...


@runtime_checkable
class RuntimeConfigPort(Protocol):
    async def get(self, key: str) -> JsonPayload | None: ...


@runtime_checkable
class ModuleBindingPort(Protocol):
    async def validate(
        self,
        module_ids: tuple[str, ...],
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> tuple[RuntimeIssue, ...]: ...

    async def build(
        self,
        module_id: str,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> ModuleInvocation: ...


@runtime_checkable
class ModuleExecutorPort(Protocol):
    async def execute(self, module_id: str, invocation: ModuleInvocation) -> ModuleExecutionResult: ...
