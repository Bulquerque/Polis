from datetime import date
from pathlib import Path

import yaml


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def load_registry(name: str) -> dict:
    root = workspace_root()
    path = root / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1" / "source_of_truth" / "registries" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_external_source_registry_declares_primary_and_fallback_roles():
    registry = load_registry("external_data_source_registry.yaml")
    primary = registry["primary_source"]
    fallbacks = registry["fallbacks"]

    assert primary["source_id"] == "london_strategic_edge"
    assert primary["role"] == "primary_market_data"
    assert primary["direct_consumer_phases"] == ["phase_01_ingestion"]
    assert primary["promotion_gate"] == "phase_02_quality_pit"
    assert len(primary["required_metadata"]) >= 8
    assert len({item["source_id"] for item in fallbacks}) == len(fallbacks)
    assert all(item["phase_owner"] == "phase_01_ingestion" for item in fallbacks)
    assert "direct_external_access_outside_phase_01_forbidden" in registry["rules"]


def test_llm_registry_uses_exact_ids_and_non_overlapping_policy_windows():
    registry = load_registry("llm_model_registry.yaml")
    intervals = registry["policy_intervals"]
    expected = {
        "mistralai/mixtral-8x7b-instruct-v0.1",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.3-70b-instruct",
        "openai/gpt-oss-120b",
        "mistralai/mistral-large-3-675b-instruct-2512",
        "qwen/qwen3.5-397b-a17b",
        "deepseek-ai/deepseek-v4-pro",
        "z-ai/glm-5.2",
    }
    assert {item["model_id"] for item in intervals} == expected
    for previous, current in zip(intervals, intervals[1:]):
        previous_until = date.fromisoformat(previous["effective_until"])
        current_from = date.fromisoformat(current["effective_from"])
        assert (current_from - previous_until).days == 1
    assert intervals[0]["effective_from"] is None
    assert intervals[-1]["effective_until"] is None
    assert all(item["evidence_status"] for item in intervals)
    assert "agent_must_not_select_model_id_directly" in registry["fallback_rules"]
