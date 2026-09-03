from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import (
    ArtifactRef,
    GraphEdge,
    GraphNode,
    GraphProposalBatch,
    ProviderDescriptor,
    PublicationResult,
)


class ArtifactStorePort(Protocol):
    def put_bytes(self, *, artifact_type: str, content: bytes, media_type: str, suffix: str, record_count: int | None, format_version: str) -> ArtifactRef: ...
    def get_bytes(self, reference: ArtifactRef) -> bytes: ...


class EventSinkPort(Protocol):
    def emit(self, event: str, dimensions: dict[str, object]) -> None: ...


class GraphProposalProviderPort(Protocol):
    async def describe(self) -> ProviderDescriptor: ...
    async def propose(self, chunks: Sequence[dict[str, object]]) -> GraphProposalBatch: ...


class GraphPublisherPort(Protocol):
    async def publish(self, *, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge], database: str | None) -> PublicationResult: ...
