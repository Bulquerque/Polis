from __future__ import annotations

import os
import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..canonical import content_hash, sha256_bytes
from ..errors import ErrorCategory, PersistenceFailureError, error
from ..models import ArtifactRef, GraphEdge, GraphNode, PublicationResult, PublicationStatus


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}

    def put_bytes(self, *, artifact_type: str, content: bytes, media_type: str, suffix: str, record_count: int | None, format_version: str) -> ArtifactRef:
        digest = sha256_bytes(content)
        uri = f"memory://{artifact_type}/{digest}{suffix}"
        self._values[uri] = bytes(content)
        return ArtifactRef(artifact_type=artifact_type, uri=uri, content_hash=digest, media_type=media_type, size_bytes=len(content), record_count=record_count, format_version=format_version)

    def get_bytes(self, reference: ArtifactRef) -> bytes:
        try:
            content = self._values[reference.uri]
        except KeyError as exc:
            raise PersistenceFailureError(error("P3_S13_ARTIFACT_NOT_FOUND", ErrorCategory.PERSISTENCE, "artifact not found in memory store", context={"uri": reference.uri})) from exc
        if sha256_bytes(content) != reference.content_hash:
            raise PersistenceFailureError(error("P3_S13_ARTIFACT_HASH_MISMATCH", ErrorCategory.PERSISTENCE, "artifact hash mismatch", context={"uri": reference.uri}))
        return content

    def preload(self, reference: ArtifactRef, content: bytes) -> None:
        self._values[reference.uri] = bytes(content)

    def tamper(self, uri: str, content: bytes) -> None:
        self._values[uri] = content


class FileArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, *, artifact_type: str, content: bytes, media_type: str, suffix: str, record_count: int | None, format_version: str) -> ArtifactRef:
        digest = sha256_bytes(content)
        directory = self._root / artifact_type / digest
        target = directory / f"data{suffix}"
        directory.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
                    temp = Path(handle.name)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, target)
            except OSError as exc:
                raise PersistenceFailureError(error("P3_S13_ARTIFACT_WRITE_FAILED", ErrorCategory.PERSISTENCE, "failed to atomically publish graph artifact")) from exc
        return ArtifactRef(artifact_type=artifact_type, uri=target.as_uri(), content_hash=digest, media_type=media_type, size_bytes=len(content), record_count=record_count, format_version=format_version)

    def get_bytes(self, reference: ArtifactRef) -> bytes:
        parsed = urlparse(reference.uri)
        if parsed.scheme != "file":
            raise PersistenceFailureError(error("P3_S13_UNSUPPORTED_ARTIFACT_URI", ErrorCategory.PERSISTENCE, "unsupported artifact URI scheme"))
        path_text = unquote(parsed.path)
        if os.name == "nt" and path_text.startswith("/") and len(path_text) >= 3 and path_text[2] == ":":
            path_text = path_text[1:]
        path = Path(path_text)
        content = path.read_bytes()
        if sha256_bytes(content) != reference.content_hash:
            raise PersistenceFailureError(error("P3_S13_ARTIFACT_HASH_MISMATCH", ErrorCategory.PERSISTENCE, "persisted graph artifact hash mismatch"))
        return content


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, dimensions: dict[str, object]) -> None:
        self.events.append((event, dict(dimensions)))


class NullGraphPublisher:
    async def publish(self, *, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge], database: str | None) -> PublicationResult:
        return PublicationResult(status=PublicationStatus.NOT_REQUESTED, adapter_id="null_graph_publisher", database=database)


class LocalFileGraphPublisher:
    """Publish the graph to deterministic local JSONL files.

    This is the supported no-server replacement for Neo4j in the local P3
    profile.  It keeps the graph portable, content-addressed and auditable;
    Neo4j remains an optional adapter for deployments that explicitly need it.
    """

    _SAFE_DATABASE = re.compile(r"^[A-Za-z0-9._-]+$")

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _jsonl(records: Sequence[object]) -> bytes:
        lines = [
            json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for record in records
        ]
        return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)
            raise PersistenceFailureError(
                error(
                    "P3_S13_LOCAL_GRAPH_WRITE_FAILED",
                    ErrorCategory.PERSISTENCE,
                    "failed to atomically publish local graph files",
                )
            ) from exc

    async def publish(
        self,
        *,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
        database: str | None,
    ) -> PublicationResult:
        name = database or "default"
        if not self._SAFE_DATABASE.fullmatch(name):
            raise PersistenceFailureError(
                error(
                    "P3_S13_LOCAL_GRAPH_DATABASE_INVALID",
                    ErrorCategory.PERSISTENCE,
                    "local graph database name contains unsafe path characters",
                )
            )
        ordered_nodes = tuple(sorted(nodes, key=lambda item: item.node_id))
        ordered_edges = tuple(sorted(edges, key=lambda item: item.edge_id))
        node_bytes = self._jsonl(ordered_nodes)
        edge_bytes = self._jsonl(ordered_edges)
        target = self._root / name
        self._atomic_write(target / "nodes.jsonl", node_bytes)
        self._atomic_write(target / "edges.jsonl", edge_bytes)
        manifest = {
            "schema_id": "local_graph_publication.v1",
            "adapter_id": "local_file_graph_publisher",
            "database": name,
            "node_count": len(ordered_nodes),
            "edge_count": len(ordered_edges),
            "nodes_sha256": sha256_bytes(node_bytes),
            "edges_sha256": sha256_bytes(edge_bytes),
            "content_hash": content_hash(
                {
                    "database": name,
                    "nodes_sha256": sha256_bytes(node_bytes),
                    "edges_sha256": sha256_bytes(edge_bytes),
                }
            ),
        }
        self._atomic_write(
            target / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        )
        return PublicationResult(
            status=PublicationStatus.PUBLISHED,
            adapter_id="local_file_graph_publisher",
            database=name,
            published_node_count=len(ordered_nodes),
            published_edge_count=len(ordered_edges),
        )
