from __future__ import annotations

from typing import Protocol


class EventSinkPort(Protocol):
    def emit(self, event_name: str, dimensions: dict[str, object]) -> None: ...


class CredentialResolverPort(Protocol):
    async def resolve(self, handle: str, handle_type: str) -> object: ...


class ToolCachePort(Protocol):
    async def get(self, cache_key: str) -> object | None: ...
    async def put(self, cache_key: str, value: object) -> None: ...


class RateLimiterPort(Protocol):
    async def acquire(self, provider_id: str, tool_id: str) -> bool: ...


class MCPToolExecutionPort(Protocol):
    async def call_tool(self, tool_name: str, arguments: dict[str, object]) -> object: ...
