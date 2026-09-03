from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from .canonical import canonical_json_bytes, tokenize
from .models import Chunk
from .ports import ArtifactStorePort


def serialize_chunks_jsonl(chunks: Sequence[Chunk]) -> bytes:
    lines = [canonical_json_bytes(chunk) for chunk in chunks]
    return b"\n".join(lines) + (b"\n" if lines else b"")


def build_keyword_index(chunks: Sequence[Chunk]) -> dict[str, tuple[str, ...]]:
    postings: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        for token in tokenize(chunk.content):
            postings[token].add(chunk.chunk_id)
    return {token: tuple(sorted(chunk_ids)) for token, chunk_ids in sorted(postings.items())}


def persist_chunk_catalog(chunks: Sequence[Chunk], store: ArtifactStorePort):
    return store.put_bytes(
        artifact_type="rag_chunk_catalog",
        content=serialize_chunks_jsonl(chunks),
        media_type="application/x-ndjson",
        suffix=".jsonl",
        record_count=len(chunks),
        format_version="rag_chunk.v1-jsonl",
    )


def persist_keyword_index(index: dict[str, tuple[str, ...]], store: ArtifactStorePort):
    return store.put_bytes(
        artifact_type="rag_keyword_index",
        content=canonical_json_bytes(index),
        media_type="application/json",
        suffix=".json",
        record_count=len(index),
        format_version="keyword_inverted_index.v1",
    )
