from __future__ import annotations

from collections.abc import Sequence

from .canonical import content_hash, normalize_text
from .errors import ErrorCategory, InvariantViolationError, TemporalViolationError, error
from .models import Chunk, ChunkingSettings, DocumentRecord, RunSnapshot


class DeterministicChunker:
    VERSION = "paragraph_word_window_v1"

    def __init__(self, settings: ChunkingSettings) -> None:
        self._settings = settings

    def chunk_documents(
        self,
        documents: Sequence[DocumentRecord],
        snapshot: RunSnapshot,
    ) -> tuple[Chunk, ...]:
        seen_documents: set[str] = set()
        chunks: list[Chunk] = []
        for document in sorted(documents, key=lambda item: (item.source_id, item.document_id)):
            if document.document_id in seen_documents:
                raise InvariantViolationError(
                    error(
                        "P3_S12_M01_DOCUMENT_ID_COLLISION",
                        ErrorCategory.INVARIANT,
                        "duplicate document_id in S12 input",
                        context={"document_id": document.document_id},
                    )
                )
            seen_documents.add(document.document_id)
            if document.available_at > snapshot.as_of_time:
                raise TemporalViolationError(
                    error(
                        "P3_S12_M01_TEMPORAL_VIOLATION",
                        ErrorCategory.TEMPORAL,
                        "document available_at is after run as_of_time",
                        context={"document_id": document.document_id},
                    )
                )
            chunks.extend(self._chunk_document(document))

        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise InvariantViolationError(
                error(
                    "P3_S12_M01_CHUNK_ID_COLLISION",
                    ErrorCategory.INVARIANT,
                    "deterministic chunk IDs collided",
                )
            )
        return tuple(sorted(chunks, key=lambda item: (item.document_id, item.sequence_number)))

    def _chunk_document(self, document: DocumentRecord) -> list[Chunk]:
        text = normalize_text(document.content)
        words = text.split()
        if len(words) < self._settings.min_words:
            return []
        step = self._settings.max_words - self._settings.overlap_words
        chunks: list[Chunk] = []
        sequence = 0
        start = 0
        while start < len(words):
            end = min(start + self._settings.max_words, len(words))
            chunk_text = " ".join(words[start:end])
            chunk_content_hash = content_hash({"content": chunk_text})
            chunk_id = "chk_" + content_hash(
                {
                    "document_id": document.document_id,
                    "start_word": start,
                    "end_word": end,
                    "content_hash": chunk_content_hash,
                    "chunker_version": self.VERSION,
                }
            )[:32]
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    source_id=document.source_id,
                    sequence_number=sequence,
                    start_word=start,
                    end_word=end,
                    content=chunk_text,
                    content_hash=chunk_content_hash,
                    event_time=document.event_time,
                    effective_time=document.effective_time,
                    available_at=document.available_at,
                    source_quality=document.source_quality,
                    entities=tuple(sorted(set(document.entities))),
                    underlyings=tuple(sorted(set(document.underlyings))),
                    lineage_refs=tuple(sorted(set(document.lineage_refs))),
                    chunker_version=self.VERSION,
                )
            )
            sequence += 1
            if end == len(words):
                break
            start += step
        return chunks
