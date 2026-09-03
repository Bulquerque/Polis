from __future__ import annotations

from datetime import datetime, timezone

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.boundary_artifacts import (
    EntityResolutionPolicy,
    TemporalEntityResolutionIndex,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.services.entity_resolution import (
    resolve_entity,
)

from .support_s33 import build_s33_m04, load_yaml


def test_m04_builds_temporal_entity_index():
    out = build_s33_m04()
    index = out["temporal_entity_resolution_index"]
    assert index["record_count"] >= 2
    assert any(item["ticker"] == "PETR4" for item in index["records"])
    assert any(item["instrument_type"] == "OPTION_CONTRACT" for item in index["records"])


def test_resolver_resolves_exact_historical_ticker():
    out = build_s33_m04()
    index = TemporalEntityResolutionIndex.model_validate(out["temporal_entity_resolution_index"], strict=False)
    policy = EntityResolutionPolicy.model_validate(out["entity_resolution_policy"], strict=False)
    result = resolve_entity(
        "PETR4",
        decision_time=datetime(2024, 1, 15, tzinfo=timezone.utc),
        index=index,
        policy=policy,
        venue="B3",
    )
    assert result.status.value in {"RESOLVED", "AMBIGUOUS"}
    assert result.candidates


def test_future_ticker_mapping_is_not_visible_in_past():
    config = load_yaml("config/research_tools/ENTITY_UNDERLYING_MAP.yaml")
    config = {**config, "records": [{
        "entity_id": "FUTURE_CO",
        "instrument_id": "FUTURE1",
        "instrument_type": "EQUITY",
        "venue": "B3",
        "ticker": "FUTR3",
        "aliases": ["Future Company"],
        "identifiers": {"ISIN": "BRFUTRACNOR0"},
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_to": None,
        "underlying_instrument_id": None,
    }]}
    out = build_s33_m04(overrides={"entity_underlying_map_config": config})
    index = TemporalEntityResolutionIndex.model_validate(out["temporal_entity_resolution_index"], strict=False)
    policy = EntityResolutionPolicy.model_validate(out["entity_resolution_policy"], strict=False)
    result = resolve_entity(
        "FUTR3",
        decision_time=datetime(2024, 1, 15, tzinfo=timezone.utc),
        index=index,
        policy=policy,
    )
    assert result.status.value == "UNRESOLVED"


def test_ambiguous_alias_is_returned_not_silently_chosen():
    config = load_yaml("config/research_tools/ENTITY_UNDERLYING_MAP.yaml")
    config = {**config, "records": [
        {"entity_id": "A", "instrument_id": "A1", "instrument_type": "EQUITY", "venue": "B3", "ticker": "AAA3", "aliases": ["Shared Alias"], "identifiers": {}, "valid_from": "2020-01-01T00:00:00Z", "valid_to": None, "underlying_instrument_id": None},
        {"entity_id": "B", "instrument_id": "B1", "instrument_type": "EQUITY", "venue": "B3", "ticker": "BBB3", "aliases": ["Shared Alias"], "identifiers": {}, "valid_from": "2020-01-01T00:00:00Z", "valid_to": None, "underlying_instrument_id": None},
    ]}
    out = build_s33_m04(overrides={"entity_underlying_map_config": config})
    index = TemporalEntityResolutionIndex.model_validate(out["temporal_entity_resolution_index"], strict=False)
    policy = EntityResolutionPolicy.model_validate(out["entity_resolution_policy"], strict=False)
    result = resolve_entity(
        "Shared Alias",
        decision_time=datetime(2024, 1, 15, tzinfo=timezone.utc),
        index=index,
        policy=policy,
    )
    assert result.status.value == "AMBIGUOUS"
    assert len(result.candidates) == 2


def test_entity_index_is_deterministic():
    first = build_s33_m04()
    second = build_s33_m04()
    assert first["temporal_entity_resolution_index"]["content_hash"] == second["temporal_entity_resolution_index"]["content_hash"]
