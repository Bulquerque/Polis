"""Deterministic in-memory adapters for tests and local orchestration."""

from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_contracts.canonical import raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.state import AccountSnapshot, PortfolioStateProjection

from ..errors import ExternalSystemError, HashMismatchError


class InMemoryArtifactStore:
    def __init__(self, artifacts: dict[str, bytes] | None = None) -> None:
        self._artifacts = dict(artifacts or {})

    def put(self, reference: ArtifactReference, data: bytes) -> None:
        if raw_sha256(data) != reference.content_sha256:
            raise HashMismatchError(f"artifact bytes do not match reference: {reference.artifact_id}")
        self._artifacts[reference.artifact_id] = data

    def read(self, reference: ArtifactReference) -> bytes:
        try:
            return self._artifacts[reference.artifact_id]
        except KeyError as exc:
            raise ExternalSystemError(f"artifact not found: {reference.artifact_id}") from exc

    def export(self) -> dict[str, bytes]:
        """Return a defensive copy for deterministic test/fixture construction."""
        return dict(self._artifacts)


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def is_applied(self, key: str) -> bool:
        return key in self._keys

    def mark_applied(self, key: str) -> None:
        self._keys.add(key)


class StaticPortfolioStateReader:
    def __init__(self, state: PortfolioStateProjection) -> None:
        self._state = state

    def read(self, *, as_of_time: datetime) -> PortfolioStateProjection:
        del as_of_time
        return self._state


class StaticAccountSnapshotAdapter:
    def __init__(self, snapshot: AccountSnapshot | None) -> None:
        self._snapshot = snapshot

    def read(self, *, as_of_time: datetime) -> AccountSnapshot | None:
        del as_of_time
        return self._snapshot
