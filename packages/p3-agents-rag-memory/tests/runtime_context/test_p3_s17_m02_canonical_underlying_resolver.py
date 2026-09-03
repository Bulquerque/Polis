from __future__ import annotations

import copy
import importlib

from .s17_test_support import deep_copy_inputs


def _m01():
    return importlib.import_module(
        "quant_pipeline.phase_03_agents_rag_memory.modules."
        "P3_S17_M01_external_stimulus_builder"
    )


def _m02():
    return importlib.import_module(
        "quant_pipeline.phase_03_agents_rag_memory.modules."
        "P3_S17_M02_canonical_underlying_resolver"
    )


def test_m02_resolves_exact_mapping_and_records_version(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    external = _m01().run_module(inputs)
    resolved = _m02().run_module(
        {
            "external_stimulus_stream": external,
            "entity_underlying_map_config": inputs["entity_underlying_map_config"],
            "proposition_registry_config": inputs["proposition_registry_config"],
        }
    )
    item = resolved["items"][0]
    assert item["resolution_status"] == "RESOLVED_ONE"
    assert item["selected_underlying_id"] == "figi:BBG000B9XRY4"
    assert item["mapping_version"] == inputs["entity_underlying_map_config"]["version"]


def test_m02_preserves_unresolved_instead_of_inventing_ticker(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    record = inputs["pit_validated_context"]["records"][0]
    record["record_id"] = "ctx:macro-test"
    record["source_event_id"] = "event:macro-test"
    record["subject"] = "Unmapped macro release"
    record["entity_ids"] = []
    record["identifier_hints"] = []
    record["proposition_id"] = None
    record["horizon"] = None
    external = _m01().run_module(inputs)
    resolved = _m02().run_module(
        {
            "external_stimulus_stream": external,
            "entity_underlying_map_config": inputs["entity_underlying_map_config"],
            "proposition_registry_config": inputs["proposition_registry_config"],
        }
    )
    item = resolved["items"][0]
    assert item["resolution_status"] == "UNRESOLVED"
    assert item["selected_underlying_id"] is None
    assert "UNDERLYING_UNRESOLVED" in item["warnings"]


def test_m02_preserves_explicit_weighted_one_to_many(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    mapping = copy.deepcopy(inputs["entity_underlying_map_config"]["mappings"][0])
    mapping["mapping_id"] = "map:apple-weighted-test"
    mapping["resolutions"] = [
        {"underlying_id": "figi:ONE", "weight": 0.6, "mic": "XNAS"},
        {"underlying_id": "figi:TWO", "weight": 0.4, "mic": "XNYS"},
    ]
    inputs["entity_underlying_map_config"]["mappings"] = [mapping]
    external = _m01().run_module(inputs)
    resolved = _m02().run_module(
        {
            "external_stimulus_stream": external,
            "entity_underlying_map_config": inputs["entity_underlying_map_config"],
            "proposition_registry_config": inputs["proposition_registry_config"],
        }
    )
    item = resolved["items"][0]
    assert item["resolution_status"] == "RESOLVED_MANY"
    assert [candidate["weight"] for candidate in item["underlying_candidates"]] == [0.6, 0.4]


def test_m02_does_not_mutate_frozen_mapping(plan_root) -> None:
    import copy
    inputs = deep_copy_inputs(plan_root)
    original_mapping = copy.deepcopy(inputs["entity_underlying_map_config"])
    external = _m01().run_module(inputs)
    resolved = _m02().run_module(
        {
            "external_stimulus_stream": external,
            "entity_underlying_map_config": inputs["entity_underlying_map_config"],
            "proposition_registry_config": inputs["proposition_registry_config"],
        }
    )
    assert inputs["entity_underlying_map_config"] == original_mapping
    assert resolved["items"][0]["mapping_version"] == original_mapping["version"]
