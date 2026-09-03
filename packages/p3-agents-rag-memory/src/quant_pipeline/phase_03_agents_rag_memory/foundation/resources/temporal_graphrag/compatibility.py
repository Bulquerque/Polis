from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from .models import GraphConfig, PitValidatedContext, ProviderRegistry, RagIndexArtifact, RunSnapshot

T = TypeVar("T", bound=BaseModel)


def _normalize(model: type[T], value: T | dict[str, Any]) -> T:
    return value if isinstance(value, model) else model.model_validate(value, strict=False)


def normalize_rag_index(value: RagIndexArtifact | dict[str, Any]) -> RagIndexArtifact:
    return _normalize(RagIndexArtifact, value)


def normalize_pit_context(value: PitValidatedContext | dict[str, Any]) -> PitValidatedContext:
    return _normalize(PitValidatedContext, value)


def normalize_run_snapshot(value: RunSnapshot | dict[str, Any]) -> RunSnapshot:
    return _normalize(RunSnapshot, value)


def normalize_graph_config(value: GraphConfig | dict[str, Any]) -> GraphConfig:
    return _normalize(GraphConfig, value)


def normalize_provider_registry(value: ProviderRegistry | dict[str, Any]) -> ProviderRegistry:
    return _normalize(ProviderRegistry, value)
