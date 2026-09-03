from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.document_rag.models import (
    ArtifactRef,
    CapabilityStatus as S12CapabilityStatus,
    Chunk,
    RetrievalIndexManifest,
)

from .canonical import content_hash, sha256_bytes
from .errors import CorpusToolError, ErrorCategory, error
from .models import (
    CapabilityReadiness,
    CapabilityStatus,
    CorpusArtifactRef,
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
    QualificationStatus,
)
from .ports import ArtifactBytesPort, CorpusRepositoryPort


@dataclass(frozen=True, slots=True)
class LoadedCorpusIndex(CorpusRepositoryPort):
    _chunks: tuple[Chunk, ...]
    _keyword_index: Mapping[str, tuple[str, ...]]
    _metadata_by_document: Mapping[str, Mapping[str, object]]
    _by_id: Mapping[str, Chunk] = field(init=False, repr=False)
    _by_document: Mapping[str, tuple[Chunk, ...]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        by_id = {chunk.chunk_id: chunk for chunk in self._chunks}
        by_document: dict[str, list[Chunk]] = {}
        for chunk in self._chunks:
            by_document.setdefault(chunk.document_id, []).append(chunk)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(
            self,
            "_by_document",
            MappingProxyType(
                {
                    key: tuple(sorted(items, key=lambda item: item.sequence_number))
                    for key, items in by_document.items()
                }
            ),
        )

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    @property
    def keyword_index(self) -> Mapping[str, tuple[str, ...]]:
        return self._keyword_index

    def chunks_for_document(self, document_id: str) -> tuple[Chunk, ...]:
        return self._by_document.get(document_id, ())

    def chunk(self, chunk_id: str) -> Chunk | None:
        return self._by_id.get(chunk_id)

    def document_metadata(self, document_id: str) -> Mapping[str, object]:
        return self._metadata_by_document.get(document_id, {})

    def supports_metadata_field(self, field_name: str) -> bool:
        return any(field_name in item for item in self._metadata_by_document.values())


@dataclass(frozen=True, slots=True)
class CorpusSnapshotLoadResult:
    snapshot: CorpusIndexSnapshot
    readiness: CorpusIndexReadinessReport
    repository: LoadedCorpusIndex


class CorpusSnapshotIndexLoader:
    MODULE_ID = "P3.S35.M01"

    def __init__(self, artifact_store: ArtifactBytesPort) -> None:
        self._artifact_store = artifact_store

    def load(
        self,
        *,
        retrieval_manifest: Mapping[str, Any] | RetrievalIndexManifest,
        phase3_run_snapshot: Mapping[str, Any],
        document_metadata: Mapping[str, Mapping[str, object]] | None = None,
    ) -> CorpusSnapshotLoadResult:
        manifest = self._manifest(retrieval_manifest)
        snapshot_id, as_of_time = self._run_snapshot(phase3_run_snapshot)
        self._validate_snapshot(manifest, snapshot_id=snapshot_id, as_of_time=as_of_time)
        chunk_ref = self._required_ref(manifest, "chunk_catalog")
        keyword_ref = self._required_ref(manifest, "keyword_index")
        chunk_bytes = self._read_verified(chunk_ref)
        keyword_bytes = self._read_verified(keyword_ref)
        chunks = self._parse_chunks(chunk_bytes)
        keyword_index = self._parse_keyword_index(keyword_bytes, chunks)
        self._validate_counts(manifest, chunks)
        self._validate_chunk_times(manifest, chunks)
        vector_ref = manifest.artifact_refs.get("vector_index")
        capabilities = tuple(self._capability(item) for item in manifest.capabilities)
        base = {
            "artifact_id": f"s35_corpus_snapshot_{manifest.content_hash[:24]}",
            "run_id": manifest.run_id,
            "snapshot_id": manifest.snapshot_id,
            "as_of_time": manifest.as_of_time,
            "retrieval_manifest_id": manifest.artifact_id,
            "retrieval_manifest_hash": manifest.content_hash,
            "rag_index_artifact_hash": manifest.rag_index_artifact_hash,
            "chunk_schema_id": manifest.chunk_schema_id,
            "chunk_count": manifest.chunk_count,
            "chunk_catalog": self._artifact_ref(chunk_ref),
            "keyword_index": self._artifact_ref(keyword_ref),
            "vector_index": self._artifact_ref(vector_ref) if vector_ref else None,
            "capabilities": capabilities,
            "required_metadata_filters": manifest.required_metadata_filters,
            "configuration_hash": manifest.configuration_hash,
            "provider_fingerprints": manifest.provider_fingerprints,
            "fallback_strategy": manifest.fallback_strategy,
            "issues": manifest.issues,
        }
        snapshot = CorpusIndexSnapshot(content_hash=content_hash(base), **base)
        readiness = self._readiness(snapshot)
        repository = LoadedCorpusIndex(
            _chunks=chunks,
            _keyword_index=MappingProxyType(keyword_index),
            _metadata_by_document=MappingProxyType(
                {
                    key: MappingProxyType(dict(value))
                    for key, value in (document_metadata or {}).items()
                }
            ),
        )
        return CorpusSnapshotLoadResult(snapshot=snapshot, readiness=readiness, repository=repository)

    @staticmethod
    def _manifest(value: Mapping[str, Any] | RetrievalIndexManifest) -> RetrievalIndexManifest:
        if isinstance(value, RetrievalIndexManifest):
            return value
        try:
            return RetrievalIndexManifest.model_validate(value, strict=False)
        except ValidationError as exc:
            raise CorpusToolError(
                error(
                    "P3_RT_CONTRACT_RETRIEVAL_MANIFEST_INVALID",
                    ErrorCategory.CONTRACT,
                    "retrieval_index_manifest is invalid",
                    context={"errors": exc.errors(include_input=False)},
                )
            ) from exc

    @staticmethod
    def _run_snapshot(value: Mapping[str, Any]) -> tuple[str, datetime]:
        snapshot_id = value.get("snapshot_id")
        as_of = value.get("as_of") or value.get("as_of_time")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise CorpusToolError(
                error(
                    "P3_RT_CONTRACT_RUN_SNAPSHOT_INVALID",
                    ErrorCategory.CONTRACT,
                    "phase3_run_snapshot lacks snapshot_id",
                )
            )
        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if not isinstance(as_of, datetime) or as_of.tzinfo is None:
            raise CorpusToolError(
                error(
                    "P3_RT_CONTRACT_RUN_SNAPSHOT_INVALID",
                    ErrorCategory.CONTRACT,
                    "phase3_run_snapshot lacks timezone-aware as_of",
                )
            )
        return snapshot_id, as_of

    @staticmethod
    def _validate_snapshot(
        manifest: RetrievalIndexManifest,
        *,
        snapshot_id: str,
        as_of_time: datetime,
    ) -> None:
        if manifest.snapshot_id != snapshot_id:
            raise CorpusToolError(
                error(
                    "P3_RT_PIT_SNAPSHOT_MISMATCH",
                    ErrorCategory.TEMPORAL,
                    "retrieval manifest and run snapshot IDs differ",
                    context={"manifest": manifest.snapshot_id, "run": snapshot_id},
                )
            )
        if manifest.as_of_time != as_of_time:
            raise CorpusToolError(
                error(
                    "P3_RT_PIT_AS_OF_MISMATCH",
                    ErrorCategory.TEMPORAL,
                    "retrieval manifest and run snapshot as_of differ",
                    context={
                        "manifest": manifest.as_of_time.isoformat(),
                        "run": as_of_time.isoformat(),
                    },
                )
            )

    @staticmethod
    def _required_ref(manifest: RetrievalIndexManifest, name: str) -> ArtifactRef:
        reference = manifest.artifact_refs.get(name)
        if reference is None:
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_INDEX_COMPONENT_MISSING",
                    ErrorCategory.DATA,
                    f"required retrieval component is missing: {name}",
                )
            )
        return reference

    def _read_verified(self, reference: ArtifactRef) -> bytes:
        try:
            content = self._artifact_store.get_bytes(reference)
        except (KeyError, ValueError) as exc:
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_ARTIFACT_HASH_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "S12 artifact could not be resolved with its declared hash",
                    context={"uri": reference.uri},
                )
            ) from exc
        actual = sha256_bytes(content)
        if actual != reference.content_hash:
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_ARTIFACT_HASH_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "S12 artifact bytes do not match the manifest hash",
                    context={"uri": reference.uri, "expected": reference.content_hash, "actual": actual},
                )
            )
        return content

    @staticmethod
    def _parse_chunks(content: bytes) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                chunks.append(Chunk.model_validate_json(line, strict=False))
            except ValidationError as exc:
                raise CorpusToolError(
                    error(
                        "P3_RT_DATA_CHUNK_CATALOG_INVALID",
                        ErrorCategory.DATA,
                        "chunk catalog contains an invalid record",
                        context={"line_number": line_number, "errors": exc.errors(include_input=False)},
                    )
                ) from exc
        ids = [item.chunk_id for item in chunks]
        if len(ids) != len(set(ids)):
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_DUPLICATE_CHUNK_ID",
                    ErrorCategory.INVARIANT,
                    "chunk catalog contains duplicate chunk IDs",
                )
            )
        return tuple(sorted(chunks, key=lambda item: (item.document_id, item.sequence_number)))

    @staticmethod
    def _parse_keyword_index(
        content: bytes,
        chunks: tuple[Chunk, ...],
    ) -> dict[str, tuple[str, ...]]:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_KEYWORD_INDEX_INVALID",
                    ErrorCategory.DATA,
                    "keyword index is not valid JSON",
                )
            ) from exc
        if not isinstance(raw, dict):
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_KEYWORD_INDEX_INVALID",
                    ErrorCategory.DATA,
                    "keyword index root must be an object",
                )
            )
        valid_ids = {item.chunk_id for item in chunks}
        output: dict[str, tuple[str, ...]] = {}
        for token, values in raw.items():
            if not isinstance(token, str) or not isinstance(values, list):
                raise CorpusToolError(
                    error(
                        "P3_RT_DATA_KEYWORD_INDEX_INVALID",
                        ErrorCategory.DATA,
                        "keyword index entries must map strings to lists",
                    )
                )
            ids = tuple(str(value) for value in values)
            unknown = sorted(set(ids) - valid_ids)
            if unknown:
                raise CorpusToolError(
                    error(
                        "P3_RT_DATA_KEYWORD_INDEX_ORPHAN",
                        ErrorCategory.INVARIANT,
                        "keyword index references unknown chunks",
                        context={"token": token, "unknown": unknown[:10]},
                    )
                )
            output[token] = tuple(sorted(set(ids)))
        return output

    @staticmethod
    def _validate_counts(manifest: RetrievalIndexManifest, chunks: tuple[Chunk, ...]) -> None:
        if manifest.chunk_count != len(chunks):
            raise CorpusToolError(
                error(
                    "P3_RT_DATA_CHUNK_COUNT_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "manifest chunk_count differs from chunk catalog",
                    context={"manifest": manifest.chunk_count, "actual": len(chunks)},
                )
            )


    @staticmethod
    def _validate_chunk_times(
        manifest: RetrievalIndexManifest,
        chunks: tuple[Chunk, ...],
    ) -> None:
        future = [item.chunk_id for item in chunks if item.available_at > manifest.as_of_time]
        if future:
            raise CorpusToolError(
                error(
                    "P3_RT_PIT_FUTURE_CHUNK_IN_SNAPSHOT",
                    ErrorCategory.TEMPORAL,
                    "frozen chunk catalog contains records after manifest as_of_time",
                    context={"chunk_ids": future[:10]},
                )
            )

    @staticmethod
    def _artifact_ref(reference: ArtifactRef) -> CorpusArtifactRef:
        return CorpusArtifactRef(**reference.model_dump(mode="python"))

    @staticmethod
    def _capability(item: Any) -> CapabilityReadiness:
        status_map = {
            S12CapabilityStatus.READY: CapabilityStatus.READY,
            S12CapabilityStatus.DEGRADED: CapabilityStatus.DEGRADED,
            S12CapabilityStatus.DISABLED: CapabilityStatus.DISABLED,
            S12CapabilityStatus.DISCONNECTED: CapabilityStatus.DEGRADED,
            S12CapabilityStatus.UNQUALIFIED: CapabilityStatus.DEGRADED,
            S12CapabilityStatus.NOT_APPLICABLE: CapabilityStatus.BLOCKED,
        }
        return CapabilityReadiness(
            capability_id=item.capability_id,
            status=status_map[item.status],
            qualification_status=item.qualification_status,
            provider_id=item.provider_id,
            model_id=item.model_id,
            model_revision=item.model_revision,
            snapshot_id=item.snapshot_id,
            supported_filters=item.supported_filters,
            reason_code=item.reason_code,
        )

    @staticmethod
    def _readiness(snapshot: CorpusIndexSnapshot) -> CorpusIndexReadinessReport:
        by_id = {item.capability_id: item for item in snapshot.capabilities}
        lexical_ready = by_id["keyword_retrieval"].status is CapabilityStatus.READY
        pit_ready = by_id["available_at_filtering"].status is CapabilityStatus.READY
        semantic = by_id.get("semantic_retrieval")
        reranker = by_id.get("reranking")
        semantic_ready = semantic is not None and semantic.status is CapabilityStatus.READY
        reranker_ready = reranker is not None and reranker.status is CapabilityStatus.READY
        reasons: list[str] = list(snapshot.issues)
        if not semantic_ready:
            reasons.append("P3_RT_PROVIDER_SEMANTIC_RETRIEVAL_UNAVAILABLE")
        if not reranker_ready:
            reasons.append("P3_RT_PROVIDER_RERANKER_UNAVAILABLE")
        if not lexical_ready or not pit_ready:
            status = QualificationStatus.FAILED
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        base = {
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
            "lexical_ready": lexical_ready,
            "semantic_ready": semantic_ready,
            "reranker_ready": reranker_ready,
            "point_in_time_filter_ready": pit_ready,
            "chunk_count": snapshot.chunk_count,
            "reason_codes": tuple(sorted(set(reasons))),
        }
        return CorpusIndexReadinessReport(content_hash=content_hash(base), **base)
