from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from ..models import GraphEdge, GraphNode, PublicationResult, PublicationStatus


class AsyncNeo4jDriverLike(Protocol):
    async def execute_query(self, query: str, parameters_: dict[str, Any], database_: str | None = None) -> Any: ...


class Neo4jGraphPublisher:
    """Optional publisher. Canonical artifacts remain portable and independent of Neo4j."""

    NODE_QUERY = """
    UNWIND $rows AS row
    MERGE (n:P3GraphNode {node_id: row.node_id})
    SET n.node_type = row.node_type,
        n.canonical_name = row.canonical_name,
        n.available_at = datetime(row.available_at),
        n.valid_from = CASE WHEN row.valid_from IS NULL THEN NULL ELSE datetime(row.valid_from) END,
        n.valid_to = CASE WHEN row.valid_to IS NULL THEN NULL ELSE datetime(row.valid_to) END,
        n.ontology_version = row.ontology_version,
        n.resolution_key = row.resolution_key
    """

    EDGE_QUERY = """
    UNWIND $rows AS row
    MATCH (s:P3GraphNode {node_id: row.source_node_id})
    MATCH (t:P3GraphNode {node_id: row.target_node_id})
    MERGE (s)-[r:P3_GRAPH_EDGE {edge_id: row.edge_id}]->(t)
    SET r.relation_type = row.relation_type,
        r.available_at = datetime(row.available_at),
        r.valid_from = CASE WHEN row.valid_from IS NULL THEN NULL ELSE datetime(row.valid_from) END,
        r.valid_to = CASE WHEN row.valid_to IS NULL THEN NULL ELSE datetime(row.valid_to) END,
        r.confidence = row.confidence,
        r.ontology_version = row.ontology_version
    """

    def __init__(self, driver: AsyncNeo4jDriverLike, adapter_id: str = "neo4j_python_driver") -> None:
        self._driver = driver
        self._adapter_id = adapter_id

    async def publish(self, *, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge], database: str | None) -> PublicationResult:
        node_rows = [node.model_dump(mode="json") for node in nodes]
        edge_rows = [edge.model_dump(mode="json") for edge in edges]
        await self._driver.execute_query(self.NODE_QUERY, parameters_={"rows": node_rows}, database_=database)
        await self._driver.execute_query(self.EDGE_QUERY, parameters_={"rows": edge_rows}, database_=database)
        return PublicationResult(
            status=PublicationStatus.PUBLISHED,
            adapter_id=self._adapter_id,
            database=database,
            published_node_count=len(node_rows),
            published_edge_count=len(edge_rows),
        )
