from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.models import (
    ArtifactRef,
    Chunk,
)


class ArtifactBytesPort(Protocol):
    def get_bytes(self, reference: ArtifactRef) -> bytes:
        """Return bytes for one immutable S12 artifact reference."""


class DenseRetrievalPort(Protocol):
    @property
    def snapshot_id(self) -> str:
        """Return the immutable vector-index snapshot identifier."""

    def search(
        self,
        query: str,
        *,
        candidate_chunk_ids: Sequence[str],
        top_k: int,
    ) -> Mapping[str, float]:
        """Return non-negative semantic scores keyed by chunk ID."""


class RerankerPort(Protocol):
    @property
    def snapshot_id(self) -> str:
        """Return the immutable reranker/model snapshot identifier."""

    def rank(self, query: str, passages: tuple[str, ...]) -> tuple[float, ...]:
        """Return one score per passage, preserving input order."""


class RawEvidenceResolverPort(Protocol):
    def resolve_document(
        self,
        *,
        document_id: str,
        expected_lineage_refs: tuple[str, ...],
        decision_time: datetime,
    ) -> tuple[bytes, str]:
        """Resolve authorized P1 bytes and return bytes plus content hash."""


class ProvenanceQueryPort(Protocol):
    def document_provenance(
        self,
        document_id: str,
        *,
        decision_time: datetime,
    ) -> dict[str, object]:
        """Return PIT-authorized P1/P2 provenance metadata for one document."""


class CorpusRepositoryPort(Protocol):
    @property
    def chunks(self) -> tuple[Chunk, ...]:
        """Return immutable corpus chunks."""

    @property
    def keyword_index(self) -> Mapping[str, tuple[str, ...]]:
        """Return immutable keyword postings."""

    def chunks_for_document(self, document_id: str) -> tuple[Chunk, ...]:
        """Return chunks for one document in sequence order."""

    def chunk(self, chunk_id: str) -> Chunk | None:
        """Return one chunk by ID."""

    def document_metadata(self, document_id: str) -> Mapping[str, object]:
        """Return normalized P2 metadata when available."""

    def supports_metadata_field(self, field_name: str) -> bool:
        """Return whether the repository can enforce one metadata filter."""
