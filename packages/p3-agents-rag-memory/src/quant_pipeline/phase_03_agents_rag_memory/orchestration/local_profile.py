"""Explicit local composition for a no-cloud Phase 3 run."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..foundation.resources.temporal_graphrag.adapters import (
    FileArtifactStore,
    ListEventSink,
    LocalFileGraphPublisher,
)


@dataclass(frozen=True, slots=True)
class LocalP3Resources:
    """Persistent local resources used by LIVE/qualification P3 modules.

    The root is supplied by the caller so the runtime never silently writes to
    the source tree, a temporary directory, or an external object store.
    """

    root: Path
    artifact_store: FileArtifactStore
    graph_publisher: LocalFileGraphPublisher
    event_sink: ListEventSink

    @classmethod
    def create(cls, root: Path) -> "LocalP3Resources":
        resolved = root.resolve()
        return cls(
            root=resolved,
            artifact_store=FileArtifactStore(resolved / "artifacts"),
            graph_publisher=LocalFileGraphPublisher(resolved / "graph"),
            event_sink=ListEventSink(),
        )

    def s13_runtime(self) -> dict[str, object]:
        """Return the explicit runtime injection required by P3.S13 LIVE."""
        return {
            "artifact_store": self.artifact_store,
            "graph_publisher": self.graph_publisher,
            "event_sink": self.event_sink,
        }


def build_local_p3_s13_runtime(root: Path) -> dict[str, object]:
    """Build the local P3.S13 runtime without a Neo4j or object-store service."""
    return LocalP3Resources.create(root).s13_runtime()


__all__ = ["LocalP3Resources", "build_local_p3_s13_runtime"]
