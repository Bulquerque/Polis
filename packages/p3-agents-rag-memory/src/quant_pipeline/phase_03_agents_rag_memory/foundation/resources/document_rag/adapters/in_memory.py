from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ..canonical import canonical_json_bytes, content_hash, l2_normalize, sha256_bytes, tokenize
from ..errors import ErrorCategory, ProviderFailureError, error
from ..models import (
    ArtifactRef,
    CapabilityStatus,
    Chunk,
    EmbeddingBatch,
    IndexComponent,
    ProviderDescriptor,
    ProviderStatus,
    VectorSnapshot,
)
from ..ports import ArtifactStorePort


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}

    def put_bytes(
        self,
        *,
        artifact_type: str,
        content: bytes,
        media_type: str,
        suffix: str,
        record_count: int | None,
        format_version: str,
    ) -> ArtifactRef:
        digest = sha256_bytes(content)
        uri = f"memory://{artifact_type}/{digest}{suffix}"
        self._values[uri] = bytes(content)
        return ArtifactRef(
            artifact_type=artifact_type,
            uri=uri,
            content_hash=digest,
            media_type=media_type,
            size_bytes=len(content),
            record_count=record_count,
            format_version=format_version,
        )

    def get_bytes(self, reference: ArtifactRef) -> bytes:
        content = self._values[reference.uri]
        if sha256_bytes(content) != reference.content_hash:
            raise ValueError("hash mismatch")
        return content

    def tamper(self, uri: str, content: bytes) -> None:
        self._values[uri] = content


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, dimensions: dict[str, object]) -> None:
        self.events.append((event, dict(dimensions)))


class HashingEmbeddingProvider:
    """Deterministic offline baseline. It is not a semantic production model."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be >= 8")
        self._dimensions = dimensions

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="offline_hashing",
            interface_id="EmbeddingProvider",
            adapter_id="hashing_embedding",
            adapter_version="1.0.0",
            status=ProviderStatus.CONNECTED_QUALIFIED,
            model_id="hashing-word-projection",
            model_revision="1",
            dimensions=self._dimensions,
            supports_batching=True,
            qualification_status="QUALIFIED_LOCAL_BASELINE_ONLY",
            fingerprint=content_hash({"adapter": "hashing_embedding", "dimensions": self._dimensions}),
            metadata={"semantic_quality": "BASELINE_ONLY", "input_type": "passage"},
        )

    async def embed_passages(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            values = [0.0] * self._dimensions
            for token in tokenize(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
                index = int.from_bytes(digest[:4], "big") % self._dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                values[index] += sign
            vectors.append(l2_normalize(values))
        descriptor = await self.describe()
        return EmbeddingBatch(
            vectors=tuple(vectors),
            provider=descriptor,
            request_hash=content_hash({"texts": list(texts), "provider": descriptor.fingerprint}),
        )


class DisabledEmbeddingProvider:
    def __init__(self, provider_id: str = "offline_hashing") -> None:
        self._provider_id = provider_id

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self._provider_id,
            interface_id="EmbeddingProvider",
            adapter_id="disabled_embedding",
            adapter_version="1.0.0",
            status=ProviderStatus.DISABLED,
            supports_batching=False,
            qualification_status="DISABLED",
            fingerprint=content_hash({"provider_id": self._provider_id, "status": "disabled"}),
        )

    async def embed_passages(self, texts: Sequence[str]) -> EmbeddingBatch:
        raise ProviderFailureError(
            error(
                "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE",
                ErrorCategory.PROVIDER,
                "embedding provider is disabled",
            )
        )


class JsonVectorStore:
    """Portable baseline vector snapshot stored as canonical JSON."""

    ADAPTER_ID = "json_vector_store"
    ADAPTER_VERSION = "1.0.0"

    async def build(
        self,
        *,
        chunks: Sequence[Chunk],
        embeddings: EmbeddingBatch,
        artifact_store: ArtifactStorePort,
        supported_filters: tuple[str, ...],
    ) -> VectorSnapshot:
        if len(chunks) != len(embeddings.vectors):
            raise ValueError("chunk/vector cardinality mismatch")
        payload = [
            {
                "chunk_id": chunk.chunk_id,
                "vector": list(vector),
                "payload": {
                    "available_at": chunk.available_at.isoformat(),
                    "source_id": chunk.source_id,
                    "document_id": chunk.document_id,
                    "underlyings": list(chunk.underlyings),
                    "entities": list(chunk.entities),
                },
            }
            for chunk, vector in zip(chunks, embeddings.vectors, strict=True)
        ]
        content = canonical_json_bytes(payload)
        reference = artifact_store.put_bytes(
            artifact_type="rag_vector_index",
            content=content,
            media_type="application/json",
            suffix=".json",
            record_count=len(payload),
            format_version="json_vector_snapshot.v1",
        )
        dimensions = len(embeddings.vectors[0]) if embeddings.vectors else embeddings.provider.dimensions
        component = IndexComponent(
            name="vector_index",
            status=CapabilityStatus.READY,
            artifact_ref=reference,
            adapter_id=self.ADAPTER_ID,
            adapter_version=self.ADAPTER_VERSION,
            model_id=embeddings.provider.model_id,
            model_revision=embeddings.provider.model_revision,
            dimensions=dimensions,
            record_count=len(payload),
            snapshot_id=reference.content_hash,
            supported_filters=supported_filters,
            qualification_status="QUALIFIED_LOCAL_BASELINE_ONLY",
        )
        return VectorSnapshot(component=component)
