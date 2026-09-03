from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import ArtifactRef, Chunk, EmbeddingBatch, ProviderDescriptor, VectorSnapshot


class ArtifactStorePort(Protocol):
    def put_bytes(
        self,
        *,
        artifact_type: str,
        content: bytes,
        media_type: str,
        suffix: str,
        record_count: int | None,
        format_version: str,
    ) -> ArtifactRef: ...

    def get_bytes(self, reference: ArtifactRef) -> bytes: ...


class EmbeddingProviderPort(Protocol):
    async def describe(self) -> ProviderDescriptor: ...

    async def embed_passages(self, texts: Sequence[str]) -> EmbeddingBatch: ...


class VectorStorePort(Protocol):
    async def build(
        self,
        *,
        chunks: Sequence[Chunk],
        embeddings: EmbeddingBatch,
        artifact_store: ArtifactStorePort,
        supported_filters: tuple[str, ...],
    ) -> VectorSnapshot: ...


class EventSinkPort(Protocol):
    def emit(self, event: str, dimensions: dict[str, object]) -> None: ...
