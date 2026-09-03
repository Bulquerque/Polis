from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from ..canonical import content_hash
from ..models import (
    ConnectivityStatus,
    DiscoveredTool,
    DiscoverySnapshot,
    ProviderAdapter,
)


class ClockPort(Protocol):
    def now(self) -> datetime:
        ...


class McpSessionLike(Protocol):
    async def list_tools(self, cursor: str | None = None) -> object:
        ...


def _read(value: object, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def normalize_mcp_tool(raw: object) -> DiscoveredTool:
    name = _read(raw, "name")
    input_schema = _read(raw, "inputSchema", "input_schema")
    if not isinstance(name, str) or not name:
        raise ValueError("MCP tool name must be a non-empty string")
    if not isinstance(input_schema, dict):
        raise ValueError("MCP tool inputSchema must be an object")
    output_schema = _read(raw, "outputSchema", "output_schema")
    annotations = _read(raw, "annotations", default={}) or {}
    if output_schema is not None and not isinstance(output_schema, dict):
        raise ValueError("MCP tool outputSchema must be an object when present")
    if not isinstance(annotations, dict):
        annotations = {"untrusted_raw": str(annotations)}
    return DiscoveredTool(
        name=name,
        title=_read(raw, "title"),
        description=_read(raw, "description", default="") or "",
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=annotations,
    )


class McpSessionDiscoveryAdapter:
    """Normalize MCP tools/list without coupling the domain to a specific SDK release."""

    def __init__(
        self,
        *,
        session: McpSessionLike,
        clock: ClockPort,
        protocol_version: str,
        list_changed_supported: bool,
        max_pages: int = 100,
    ) -> None:
        self._session = session
        self._clock = clock
        self._protocol_version = protocol_version
        self._list_changed_supported = list_changed_supported
        self._max_pages = max_pages

    async def discover(self, provider: ProviderAdapter) -> DiscoverySnapshot:
        tools: list[DiscoveredTool] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(self._max_pages):
            response = await self._session.list_tools(cursor=cursor)
            raw_tools = _read(response, "tools", default=()) or ()
            tools.extend(normalize_mcp_tool(tool) for tool in raw_tools)
            next_cursor = _read(response, "nextCursor", "next_cursor")
            if next_cursor is None:
                cursor = None
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise ValueError("MCP tools/list returned an invalid cursor")
            if next_cursor in seen_cursors:
                raise ValueError("MCP tools/list cursor repeated; refusing infinite pagination")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise ValueError("MCP tools/list exceeded max_pages")

        observed_at = self._clock.now()
        if observed_at.tzinfo is None:
            raise ValueError("clock must return timezone-aware datetime")
        payload = {
            "provider_id": provider.provider_id,
            "protocol": provider.protocol,
            "protocol_version": self._protocol_version,
            "observed_at": observed_at,
            "connectivity_status": ConnectivityStatus.CONNECTED,
            "list_changed_supported": self._list_changed_supported,
            "tools": tuple(sorted(tools, key=lambda item: item.name)),
            "next_cursor_exhausted": cursor is None,
            "issues": (),
        }
        return DiscoverySnapshot(fingerprint=content_hash(payload), **payload)
