from __future__ import annotations

from ..models import DiscoverySnapshot, ProviderAdapter


class StaticDiscoveryAdapter:
    def __init__(self, snapshots: dict[str, DiscoverySnapshot]) -> None:
        self._snapshots = dict(snapshots)

    async def discover(self, provider: ProviderAdapter) -> DiscoverySnapshot:
        try:
            return self._snapshots[provider.provider_id]
        except KeyError as exc:
            raise RuntimeError(f"no frozen discovery snapshot for {provider.provider_id}") from exc


class NoopDiscoveryAdapter:
    async def discover(self, provider: ProviderAdapter) -> DiscoverySnapshot:
        raise RuntimeError(f"tool discovery disabled for {provider.provider_id}")
