from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..contracts import ArtifactPointer, FoundationRuntimeManifest
from ..contracts.integration import (
    CycleKernelRequest,
    CycleKernelResult,
    P3CycleClosureManifest,
    ReplayState,
    RuntimeFoundationContext,
)

T = TypeVar("T", bound=BaseModel)


class ArtifactResolverPort(Protocol):
    """Resolve and hash-verify an immutable pointer into a requested model."""

    def resolve(self, pointer: ArtifactPointer, model_type: type[T]) -> T:
        ...


class FoundationManifestResolverPort(Protocol):
    def resolve(self, manifest: FoundationRuntimeManifest) -> RuntimeFoundationContext:
        ...


class CheckpointResolverPort(Protocol):
    def resolve(self, closure: P3CycleClosureManifest) -> ReplayState:
        ...


class CycleKernelPort(Protocol):
    contract_pack_version: str

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        ...
