from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.adapters.neo4j import (
    Neo4jGraphPublisher,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.adapters import (
    LocalFileGraphPublisher,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.temporal_graphrag.errors import (
    PersistenceFailureError,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.adapters.mcp_discovery import (
    McpSessionDiscoveryAdapter,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import (
    ConnectivityStatus,
    ProviderAdapter,
    QualificationStatus,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


class FakeMcpSession:
    async def list_tools(self, cursor: str | None = None) -> object:
        assert cursor is None
        return {
            "tools": [
                {
                    "name": "lookup_evidence",
                    "description": "Read-only evidence lookup",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }


class FakeNeo4jDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str | None]] = []

    async def execute_query(
        self,
        query: str,
        parameters_: dict[str, object],
        database_: str | None = None,
    ) -> object:
        self.calls.append((query, parameters_, database_))
        return object()


def test_mcp_adapter_uses_protocol_without_sdk_dependency() -> None:
    provider = ProviderAdapter(
        provider_id="fake_mcp",
        interface_id="MCPGatewayAdapter",
        adapter_id="fake_session",
        adapter_version="1.0.0",
        protocol="MCP",
        protocol_version="2025-11-25",
        connectivity_status=ConnectivityStatus.CONNECTED,
        qualification_status=QualificationStatus.UNQUALIFIED,
        capabilities=("tools/list",),
        fingerprint="a" * 64,
    )
    adapter = McpSessionDiscoveryAdapter(
        session=FakeMcpSession(),
        clock=FixedClock(),
        protocol_version="2025-11-25",
        list_changed_supported=False,
    )
    snapshot = asyncio.run(adapter.discover(provider))
    assert snapshot.connectivity_status is ConnectivityStatus.CONNECTED
    assert [tool.name for tool in snapshot.tools] == ["lookup_evidence"]


def test_neo4j_adapter_uses_injected_driver_without_sdk_dependency() -> None:
    driver = FakeNeo4jDriver()
    publisher = Neo4jGraphPublisher(driver)
    result = asyncio.run(publisher.publish(nodes=(), edges=(), database="neo4j"))
    assert result.published_node_count == 0
    assert result.published_edge_count == 0
    assert len(driver.calls) == 2
    assert all(call[2] == "neo4j" for call in driver.calls)


def test_local_graph_publisher_is_deterministic_and_serverless(tmp_path) -> None:
    publisher = LocalFileGraphPublisher(tmp_path)
    result = asyncio.run(publisher.publish(nodes=(), edges=(), database="local"))
    assert result.adapter_id == "local_file_graph_publisher"
    assert result.published_node_count == 0
    assert result.published_edge_count == 0
    assert (tmp_path / "local" / "nodes.jsonl").read_bytes() == b""
    assert (tmp_path / "local" / "edges.jsonl").read_bytes() == b""
    manifest = (tmp_path / "local" / "manifest.json").read_text(encoding="utf-8")
    assert "local_graph_publication.v1" in manifest


def test_local_graph_publisher_rejects_path_traversal(tmp_path) -> None:
    publisher = LocalFileGraphPublisher(tmp_path)
    with pytest.raises(PersistenceFailureError):
        asyncio.run(publisher.publish(nodes=(), edges=(), database="../outside"))
