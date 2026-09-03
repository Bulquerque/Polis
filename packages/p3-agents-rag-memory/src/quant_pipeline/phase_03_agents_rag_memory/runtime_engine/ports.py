from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Mapping, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from .contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    CycleKernelResult,
    FoundationRuntimeManifest,
    P3CycleClosureManifest,
    ReplayState,
    ResolvedArtifact,
    RuntimeFoundationContext,
    RuntimeIssue,
)

if TYPE_CHECKING:
    from .kernel import CapabilityExecution

RequestT = TypeVar("RequestT", contravariant=True)
ResponseT = TypeVar("ResponseT", covariant=True)
ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


@runtime_checkable
class ClockPort(Protocol):
    """Provide timezone-aware timestamps without coupling domain code to wall-clock time."""

    def now(self) -> datetime: ...


@runtime_checkable
class LLMPort(Protocol[RequestT, ResponseT]):
    """Generate a typed model response from a typed cognition request."""

    async def generate(self, request: RequestT) -> ResponseT: ...


@runtime_checkable
class ToolGatewayPort(Protocol[RequestT, ResponseT]):
    """Authorize and execute a tool request behind one audited boundary."""

    async def execute(self, request: RequestT) -> ResponseT: ...


@runtime_checkable
class KnowledgeRetrievalPort(Protocol[RequestT, ResponseT]):
    """Query point-in-time-safe documentary knowledge."""

    async def retrieve(self, request: RequestT) -> ResponseT: ...


@runtime_checkable
class GraphQueryPort(Protocol[RequestT, ResponseT]):
    """Query point-in-time-safe graph evidence without exposing a graph backend."""

    async def query(self, request: RequestT) -> ResponseT: ...


# Backward-compatible alias kept within runtime only.
KnowledgeIndexPort = KnowledgeRetrievalPort


@runtime_checkable
class MemoryReadPort(Protocol[RequestT, ResponseT]):
    """Read person-scoped memory under the policy governed by foundation."""

    async def read(self, request: RequestT) -> ResponseT: ...


MemoryStorePort = MemoryReadPort


@runtime_checkable
class ArtifactResolverPort(Protocol):
    """Resolve and hash-check an ArtifactPointer without leaking storage technology."""

    async def resolve(self, pointer: ArtifactPointer) -> ResolvedArtifact: ...


@runtime_checkable
class FoundationManifestResolverPort(Protocol):
    """Materialize the reference-based foundation manifest into runtime views."""

    async def resolve(self, manifest: FoundationRuntimeManifest) -> RuntimeFoundationContext: ...


@runtime_checkable
class ArtifactStorePort(Protocol[ArtifactT]):
    """Persist immutable typed artifacts and return an integration pointer."""

    async def write(self, artifact_name: str, artifact: ArtifactT) -> ArtifactPointer: ...

    async def read(self, pointer: ArtifactPointer, model: type[ArtifactT]) -> ArtifactT: ...


@runtime_checkable
class CheckpointPort(Protocol[ArtifactT]):
    """Persist and restore replay-complete cycle checkpoints."""

    async def save(self, checkpoint: ArtifactT) -> ArtifactPointer: ...

    async def load(self, pointer: ArtifactPointer, model: type[ArtifactT]) -> ArtifactT: ...


@runtime_checkable
class CheckpointResolverPort(Protocol):
    """Materialize the B cycle closure into the canonical next-cycle ReplayState."""

    async def resolve(self, closure: P3CycleClosureManifest) -> ReplayState: ...


@runtime_checkable
class CycleCapabilityPort(Protocol):
    """One of the four cohesive runtime capability boundaries (runtime capabilities)."""

    async def validate(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
    ) -> tuple[RuntimeIssue, ...]: ...

    async def execute(
        self,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> "CapabilityExecution": ...


@runtime_checkable
class CycleKernelPort(Protocol):
    """Stable foundation warm-up and Master runner boundary."""

    contract_version: str

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult: ...


@runtime_checkable
class SettingsPort(Protocol):
    """Expose an immutable, serializable configuration view."""

    def snapshot(self) -> Mapping[str, object]: ...
