"""Ports used by S1. Implementations live in adapters and later P8 subphases."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.state import AccountSnapshot, PortfolioStateProjection

from .debug import S1FailureDebugBundle


class ArtifactStorePort(Protocol):
    def read(self, reference: ArtifactReference) -> bytes:
        """Return the exact bytes identified by the content-addressed reference."""


class IdempotencyStorePort(Protocol):
    def is_applied(self, key: str) -> bool:
        """Return whether an idempotency key has already been committed."""

    def mark_applied(self, key: str) -> None:
        """Atomically mark a validated feedback item as applied."""


class PortfolioStateReaderPort(Protocol):
    def read(self, *, as_of_time: datetime) -> PortfolioStateProjection:
        """Read a replay-proven, immutable portfolio state projection."""


class AccountSnapshotPort(Protocol):
    def read(self, *, as_of_time: datetime) -> AccountSnapshot | None:
        """Read a broker/external account snapshot, or None when unavailable."""


class DebugBundleWriterPort(Protocol):
    def write_failure(self, bundle: S1FailureDebugBundle) -> str:
        """Persist a sanitized failure bundle and return its location/identifier."""
