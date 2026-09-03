from __future__ import annotations

from typing import Protocol

from .models import DiscoverySnapshot, ProviderAdapter


class ToolDiscoveryPort(Protocol):
    async def discover(self, provider: ProviderAdapter) -> DiscoverySnapshot:
        """Return a frozen discovery snapshot for one provider."""


class EventSinkPort(Protocol):
    def emit(self, event_name: str, dimensions: dict[str, object]) -> None:
        """Emit a structured observability event."""
