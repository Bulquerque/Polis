from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .canonical import content_hash, lexical_similarity, sha256_bytes, tokenize
from .models import (
    ContentMode,
    DocumentResult,
    ProvenanceEdge,
    ProvenanceNode,
    ProvenanceResult,
    VersionComparisonResult,
    VersionDifference,
)
from .ports import CorpusRepositoryPort, ProvenanceQueryPort, RawEvidenceResolverPort

RAW_FALLBACK_WARNING = "P3_RT_DATA_RAW_EVIDENCE_FALLBACK_RECONSTRUCTED"


@dataclass(frozen=True, slots=True)
class DocumentAssembly:
    document: DocumentResult | None
    warnings: tuple[str, ...] = ()


class DocumentAssembler:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        raw_resolver: RawEvidenceResolverPort | None = None,
    ) -> None:
        self._repository = repository
        self._raw_resolver = raw_resolver

    def assemble(
        self,
        *,
        document_id: str,
        decision_time: datetime,
        include_content: bool,
    ) -> DocumentAssembly:
        chunks = tuple(
            item
            for item in self._repository.chunks_for_document(document_id)
            if item.available_at <= decision_time
        )
        if not chunks:
            return DocumentAssembly(document=None)

        content, mode, document_hash, warnings = self._resolve_content(
            document_id=document_id,
            chunks=chunks,
            decision_time=decision_time,
            include_content=include_content,
        )
        event_times = [item.event_time for item in chunks if item.event_time is not None]
        effective_times = [
            item.effective_time for item in chunks if item.effective_time is not None
        ]
        document = DocumentResult(
            document_id=document_id,
            source_ids=tuple(sorted({item.source_id for item in chunks})),
            content=content,
            content_mode=mode,
            chunk_ids=tuple(item.chunk_id for item in chunks),
            available_at=max(item.available_at for item in chunks),
            event_time=min(event_times) if event_times else None,
            effective_time=min(effective_times) if effective_times else None,
            source_quality=max(item.source_quality for item in chunks),
            entities=tuple(sorted({entity for item in chunks for entity in item.entities})),
            underlyings=tuple(
                sorted({value for item in chunks for value in item.underlyings})
            ),
            lineage_refs=tuple(
                sorted({ref for item in chunks for ref in item.lineage_refs})
            ),
            document_hash=document_hash,
        )
        return DocumentAssembly(document=document, warnings=warnings)

    def _resolve_content(
        self,
        *,
        document_id: str,
        chunks: tuple[object, ...],
        decision_time: datetime,
        include_content: bool,
    ) -> tuple[str | None, ContentMode, str, tuple[str, ...]]:
        if not include_content:
            digest = content_hash(
                {
                    "document_id": document_id,
                    "chunk_hashes": [item.content_hash for item in chunks],
                }
            )
            return None, ContentMode.METADATA_ONLY, digest, ()

        if self._raw_resolver is not None:
            try:
                raw, declared_hash = self._raw_resolver.resolve_document(
                    document_id=document_id,
                    expected_lineage_refs=tuple(
                        sorted({ref for chunk in chunks for ref in chunk.lineage_refs})
                    ),
                    decision_time=decision_time,
                )
                if sha256_bytes(raw) != declared_hash:
                    raise ValueError("raw evidence hash mismatch")
                return raw.decode("utf-8"), ContentMode.RAW_AUTHORIZED, declared_hash, ()
            except (UnicodeDecodeError, LookupError, ValueError):
                content = self._reconstruct(chunks)
                digest = content_hash({"document_id": document_id, "content": content})
                return (
                    content,
                    ContentMode.RECONSTRUCTED_FROM_INDEX,
                    digest,
                    (RAW_FALLBACK_WARNING,),
                )

        content = self._reconstruct(chunks)
        digest = content_hash({"document_id": document_id, "content": content})
        return content, ContentMode.RECONSTRUCTED_FROM_INDEX, digest, ()

    @staticmethod
    def _reconstruct(chunks: tuple[object, ...]) -> str:
        return "\n".join(str(item.content) for item in chunks)


class VersionComparator:
    def compare(
        self,
        *,
        left: DocumentResult,
        right: DocumentResult,
        left_metadata: Mapping[str, object],
        right_metadata: Mapping[str, object],
    ) -> VersionComparisonResult:
        left_text = left.content or ""
        right_text = right.content or ""
        left_counts = Counter(tokenize(left_text))
        right_counts = Counter(tokenize(right_text))
        differences = tuple(
            self._difference(token, left_counts[token], right_counts[token])
            for token in sorted(set(left_counts) | set(right_counts))
            if left_counts[token] != right_counts[token]
        )
        left_group = left_metadata.get("version_group_id")
        right_group = right_metadata.get("version_group_id")
        return VersionComparisonResult(
            left_document_id=left.document_id,
            right_document_id=right.document_id,
            left_hash=left.document_hash,
            right_hash=right.document_hash,
            lexical_similarity=lexical_similarity(left_text, right_text),
            differences=differences,
            version_graph_confirmed=bool(left_group and left_group == right_group),
        )

    @staticmethod
    def _difference(token: str, left_count: int, right_count: int) -> VersionDifference:
        if left_count == 0:
            change_type = "ADDED"
        elif right_count == 0:
            change_type = "REMOVED"
        else:
            change_type = "ADDED" if right_count > left_count else "REMOVED"
        return VersionDifference(
            change_type=change_type,
            token=token,
            left_count=left_count,
            right_count=right_count,
        )


class ProvenanceAssembler:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        provenance_port: ProvenanceQueryPort | None = None,
    ) -> None:
        self._repository = repository
        self._provenance_port = provenance_port

    def build(
        self,
        *,
        document_id: str | None,
        chunk_id: str | None,
        decision_time: datetime,
    ) -> ProvenanceResult | None:
        chunk = self._repository.chunk(chunk_id) if chunk_id else None
        if chunk is not None:
            document_id = chunk.document_id
        if document_id is None:
            return None
        chunks = tuple(
            item
            for item in self._repository.chunks_for_document(document_id)
            if item.available_at <= decision_time
        )
        if not chunks:
            return None

        metadata = self._metadata(document_id, decision_time)
        nodes: dict[str, ProvenanceNode] = {}
        edges: set[tuple[str, str, str]] = set()
        source_ids = sorted({item.source_id for item in chunks})
        for source_id in source_ids:
            node_id = self._node_id("source", source_id)
            nodes[node_id] = ProvenanceNode(
                node_id=node_id,
                node_type="SOURCE",
                metadata={"source_id": source_id},
            )

        p1_node = self._add_p1_node(nodes, metadata)
        p2_node = self._add_p2_node(nodes, metadata)
        metadata_source = metadata.get("source_id")
        if isinstance(metadata_source, str):
            source_node = self._node_id("source", metadata_source)
            nodes.setdefault(
                source_node,
                ProvenanceNode(
                    node_id=source_node,
                    node_type="SOURCE",
                    metadata={"source_id": metadata_source},
                ),
            )
            if p1_node:
                edges.add((source_node, p1_node, "WAS_ATTRIBUTED_TO"))
        if p1_node and p2_node:
            edges.add((p1_node, p2_node, "WAS_DERIVED_FROM"))

        for item in chunks:
            chunk_node = self._node_id("chunk", item.chunk_id)
            nodes[chunk_node] = ProvenanceNode(
                node_id=chunk_node,
                node_type="P3_CHUNK",
                content_hash=item.content_hash,
                metadata={
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                },
            )
            if p2_node:
                edges.add((p2_node, chunk_node, "WAS_DERIVED_FROM"))
            else:
                source_node = self._node_id("source", item.source_id)
                edges.add((source_node, chunk_node, "WAS_ATTRIBUTED_TO"))

        return ProvenanceResult(
            subject_id=chunk_id or document_id,
            nodes=tuple(nodes[key] for key in sorted(nodes)),
            edges=tuple(
                ProvenanceEdge(
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                )
                for source, target, relation in sorted(edges)
            ),
            complete_to_p1=bool(p1_node and p2_node),
        )

    def _metadata(self, document_id: str, decision_time: datetime) -> dict[str, object]:
        if self._provenance_port is None:
            return {}
        return dict(
            self._provenance_port.document_provenance(
                document_id,
                decision_time=decision_time,
            )
        )

    @classmethod
    def _add_p1_node(
        cls,
        nodes: dict[str, ProvenanceNode],
        metadata: Mapping[str, object],
    ) -> str | None:
        raw_id = metadata.get("p1_raw_artifact_id")
        if not isinstance(raw_id, str):
            return None
        node_id = cls._node_id("p1", raw_id)
        raw_hash = metadata.get("p1_content_hash")
        nodes[node_id] = ProvenanceNode(
            node_id=node_id,
            node_type="P1_ARTIFACT",
            content_hash=str(raw_hash) if raw_hash else None,
            metadata={
                "raw_artifact_id": raw_id,
                "snapshot_id": metadata.get("p1_snapshot_id"),
            },
        )
        return node_id

    @classmethod
    def _add_p2_node(
        cls,
        nodes: dict[str, ProvenanceNode],
        metadata: Mapping[str, object],
    ) -> str | None:
        raw_id = metadata.get("p2_record_id")
        if not isinstance(raw_id, str):
            return None
        node_id = cls._node_id("p2", raw_id)
        nodes[node_id] = ProvenanceNode(
            node_id=node_id,
            node_type="P2_RECORD",
            metadata={"record_id": raw_id},
        )
        return node_id

    @staticmethod
    def _node_id(layer: str, raw_id: str) -> str:
        return f"{layer}:{raw_id}"
