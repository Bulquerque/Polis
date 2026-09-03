"""Materialize process-local point-in-time ports from the serialized S33 boundary."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import utc
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.boundary_artifacts import (
    ResearchDataBoundaryBundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.boundary import (
    InMemoryPitMacroBoundary,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.boundary import (
    InMemoryPitMarketBoundary,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.normalization import (
    artifact_records,
    parse_datetime,
)


class FrozenArtifactQueryPort:
    """Generic async PIT query port for company and quantitative families."""

    def __init__(
        self,
        *,
        snapshot_id: str,
        artifacts: Mapping[str, object],
        allowed_view_ids: Sequence[str],
    ) -> None:
        self.snapshot_id = snapshot_id
        self._allowed = frozenset(str(item) for item in allowed_view_ids)
        self._rows = MappingProxyType(
            {name: artifact_records(value) for name, value in artifacts.items()}
        )

    async def query(
        self,
        *,
        view_id: str,
        filters: Mapping[str, JsonValue],
        decision_time: datetime,
    ) -> Sequence[Mapping[str, JsonValue]]:
        if self._allowed and view_id not in self._allowed:
            raise KeyError(f"view is not authorized by S33 boundary: {view_id}")
        cutoff = utc(decision_time)
        visible: list[dict[str, JsonValue]] = []
        for raw in self._rows.get(view_id, ()):
            if "available_at" not in raw:
                continue
            available = parse_datetime(raw["available_at"], field="available_at")
            if available > cutoff or not self._matches(raw, filters):
                continue
            visible.append({str(key): value for key, value in raw.items()})  # type: ignore[dict-item]
        return tuple(visible)

    @staticmethod
    def _matches(row: Mapping[str, object], filters: Mapping[str, JsonValue]) -> bool:
        for field, expected in filters.items():
            if expected is None:
                continue
            actual = row.get(field)
            if isinstance(expected, (tuple, list, set, frozenset)):
                if actual not in expected:
                    return False
            elif str(actual) != str(expected):
                return False
        return True


@dataclass(frozen=True, slots=True)
class RuntimePortSet:
    services: Mapping[str, object]
    missing_required_ports: tuple[str, ...]
    materialized_ports: tuple[str, ...]


class BoundaryRuntimeFactory:
    """Build all family ports from one S33 authority plus frozen artifacts.

    Existing explicitly injected ports remain valid deployment adapters. Missing
    ports are materialized from ``research_artifacts`` whenever enough immutable
    data is available. The result is honest and fail-closed: required ports that
    cannot be built are reported instead of silently omitted.
    """

    def materialize(
        self,
        *,
        boundary_payload: object,
        context: ModuleExecutionContext,
        required_ports: Sequence[str],
    ) -> RuntimePortSet:
        boundary = ResearchDataBoundaryBundle.model_validate(boundary_payload, strict=False)
        base = dict(context.services)
        artifacts = base.get("research_artifacts", {})
        if artifacts is None:
            artifacts = {}
        if not isinstance(artifacts, Mapping):
            raise TypeError("research_artifacts service must be a mapping")
        snapshot_id = (
            context.run_identity.snapshot_id
            if context.run_identity is not None
            else str(base.get("research_snapshot_id") or boundary.artifact_id)
        )

        generic = None
        if artifacts:
            generic = FrozenArtifactQueryPort(
                snapshot_id=snapshot_id,
                artifacts=artifacts,
                allowed_view_ids=boundary.allowed_view_ids,
            )
            base.setdefault("pit_research_query_port", generic)
            base.setdefault("company_pit_query_port", generic)
            base.setdefault("quant_pit_query_port", generic)
            base.setdefault(
                "pit_market_query_port",
                InMemoryPitMarketBoundary(snapshot_id=snapshot_id, artifacts=artifacts),
            )
            base.setdefault(
                "pit_macro_query_port",
                InMemoryPitMacroBoundary(snapshot_id=snapshot_id, artifacts=artifacts),
            )

        loader = base.get("corpus_index_loader")
        if base.get("corpus_repository") is None and callable(loader):
            repository = loader(snapshot_id=snapshot_id, artifacts=artifacts)
            if repository is not None:
                base["corpus_repository"] = repository

        missing = tuple(sorted(name for name in set(required_ports) if base.get(name) is None))
        materialized = tuple(
            sorted(name for name in set(required_ports) if base.get(name) is not None)
        )
        return RuntimePortSet(
            services=MappingProxyType(base),
            missing_required_ports=missing,
            materialized_ports=materialized,
        )


__all__ = [
    "BoundaryRuntimeFactory",
    "FrozenArtifactQueryPort",
    "RuntimePortSet",
]
