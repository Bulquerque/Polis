from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class ArtifactResolverPort(Protocol):
    """Resolve an immutable artifact reference into a materialized mapping."""

    def resolve(self, artifact_reference: dict[str, Any]) -> dict[str, Any]:
        ...


class ResourceResolverPort(Protocol):
    """Resolve a declared config/schema path without global filesystem access."""

    def resolve(self, path: str) -> Any:
        ...


class ClockPort(Protocol):
    def now_utc(self) -> datetime:
        ...
