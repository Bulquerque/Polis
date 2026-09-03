from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.temporal_authority.errors import S2ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator import run_module as run_s1_m01
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M02_source_quality_context_guard import run_module as run_s1_m02
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M01_point_in_time_context_gate import run_module as run_s2_m01
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M02_phase3_run_snapshot_builder import run_module as run_s2_m02
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S2_M03_model_knowledge_cutoff_firewall import run_module as run_s2_m03


class ArtifactResolver:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def resolve(self, reference: dict[str, object]) -> object:
        return self._payload[str(reference["artifact_name"])]


class ResourceResolver:
    def __init__(self, root: Path) -> None:
        self._root = root

    def resolve(self, path: str) -> object:
        target = self._root / path
        return yaml.safe_load(target.read_text(encoding="utf-8"))


def _s1(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    payload = json.loads(
        (root / "fixtures/external_compat/p2_real_packager_fixture.json").read_text(
            encoding="utf-8"
        )
    )
    handoff = run_s1_m01(payload)["outputs"]["validated_phase2_handoff"]
    policy = yaml.safe_load(
        (root / "config/governance/SOURCE_QUALITY_POLICY.yaml").read_text(
            encoding="utf-8"
        )
    )
    validated = run_s1_m02(
        {
            "validated_phase2_handoff": handoff,
            "source_quality_panel": payload["source_quality_panel"],
            "source_quality_policy_config": policy,
        }
    )["outputs"]["validated_context_inputs"]
    return payload, validated


def _pit(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    payload, validated = _s1(root)
    evaluation_window = {
        "as_of": "2026-07-27T12:00:00Z",
        "evaluation_start": "2026-07-27T12:30:00Z",
        "evaluation_end": "2026-07-28T12:30:00Z",
        "warmup_start": "2026-07-20T00:00:00Z",
        "warmup_end": "2026-07-27T11:59:59Z",
        "timezone": "UTC",
        "boundary_rule": "available_at_equal_as_of_allowed",
    }
    pit = run_s2_m01(
        {
            "validated_context_inputs": validated,
            "evaluation_window_config": evaluation_window,
        },
        {"artifact_resolver": ArtifactResolver(payload)},
    )["outputs"]["pit_validated_context"]
    return payload, pit


def _snapshot(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    payload, pit = _pit(root)
    providers = {
        "registry_id": "provider-registry-test",
        "providers": [
            {
                "provider_id": "fixture_llm",
                "adapter_id": "fixture_adapter",
                "adapter_version": "1.0.0",
                "capabilities": ["structured_output"],
                "qualification_status": "QUALIFIED_TEST",
                "models": [
                    {
                        "model_id": "fixture/model",
                        "model_version": "1",
                        "release_date": "2025-01-01T00:00:00Z",
                        "declared_knowledge_cutoff": "2024-12-01T00:00:00Z",
                        "training_data_cutoff": "2024-11-01T00:00:00Z",
                        "canary_test_status": "PASS",
                        "qualification_status": "QUALIFIED_TEST",
                        "evidence_refs": ["fixture-evidence"],
                    }
                ],
            }
        ],
    }
    inventory = {
        "schema_registry_version": "test-v1",
        "schema_count": 1,
        "schemas": [
            {
                "schema": "pit_validated_context",
                "path": "schemas/pit_validated_context.schema.yaml",
                "class": "internal",
                "authority": "P3",
            }
        ],
    }
    snapshot = run_s2_m02(
        {
            "pit_validated_context": pit,
            "phase3_handoff_manifest": payload["phase3_handoff_manifest"],
            "config_bindings_registry": {
                "version": "test-v1",
                "bindings": {
                    "evaluation_protocol_config": "config/evaluation_protocol_config.yaml"
                },
            },
            "provider_adapter_registry_config": providers,
            "p3_schema_authority_inventory": inventory,
        },
        {
            "resource_resolver": ResourceResolver(root),
            "processed_at": "2026-07-27T12:01:00Z",
            "run_id": "run-s2-test",
            "architecture_revision": "P3-FINAL",
            "execution_profile": "QUALIFICATION",
            "execution_mode": "QUALIFICATION",
            "seed_manifest": {"status": "READY", "global_seed": 42, "component_seeds": {}, "derivation_policy": "sha256-v1"},
            "prompt_inventory": [],
            "budget_manifest": {"max_tokens": 1000},
        },
    )["outputs"]["phase3_run_snapshot"]
    return providers, snapshot


def test_pit_gate_accepts_only_information_available_at_as_of(root: Path) -> None:
    _, pit = _pit(root)
    assert pit["validation_status"] == "READY"
    assert pit["summary"]["accepted"] == 3
    assert pit["run_temporal_boundary"]["as_of"] == "2026-07-27T12:00:00Z"


def test_pit_gate_blocks_future_availability(root: Path) -> None:
    payload, validated = _s1(root)
    future_payload = copy.deepcopy(payload)
    future_payload["clean_event_reference_panel"]["records"][0]["available_at"] = "2026-07-28T00:00:00Z"
    with pytest.raises(S2ContractError, match="AVAILABLE_AT_AFTER_AS_OF"):
        run_s2_m01(
            {
                "validated_context_inputs": validated,
                "evaluation_window_config": {
                    "as_of": "2026-07-27T12:00:00Z",
                    "timezone": "UTC",
                    "boundary_rule": "available_at_equal_as_of_allowed",
                },
            },
            {
                "artifact_resolver": ArtifactResolver(future_payload),
                "strict_artifact_hashes": False,
            },
        )


def test_snapshot_is_deterministic_for_same_inputs(root: Path) -> None:
    _, first = _snapshot(root)
    _, second = _snapshot(root)
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert first["identity"]["snapshot_id"] == second["identity"]["snapshot_id"]
    assert first["identity"]["architecture_revision"] == "P3-FINAL"


def test_cutoff_firewall_accepts_known_pre_as_of_model(root: Path) -> None:
    providers, snapshot = _snapshot(root)
    report = run_s2_m03(
        {
            "phase3_run_snapshot": snapshot,
            "provider_adapter_registry_config": providers,
            "evaluation_protocol_config": yaml.safe_load(
                (root / "config/evaluation_protocol_config.yaml").read_text()
            ),
            "model_knowledge_cutoff_policy_config": yaml.safe_load(
                (root / "config/governance/model_knowledge_cutoff_policy.yaml").read_text()
            ),
        },
        {"execution_profile": "QUALIFICATION"},
    )["outputs"]["model_knowledge_cutoff_report"]
    assert report["overall_risk"] == "LOWER_RISK_KNOWN_PRE_AS_OF"
    assert report["overall_disposition"] == "ALLOWED_WITH_DISCLOSURE"


def test_cutoff_firewall_blocks_canary_contamination(root: Path) -> None:
    providers, snapshot = _snapshot(root)
    contaminated = copy.deepcopy(providers)
    contaminated["providers"][0]["models"][0]["canary_test_status"] = "DETECTED"
    with pytest.raises(S2ContractError, match="CANARY_CONTAMINATION_DETECTED"):
        run_s2_m03(
            {
                "phase3_run_snapshot": snapshot,
                "provider_adapter_registry_config": contaminated,
                "evaluation_protocol_config": yaml.safe_load(
                    (root / "config/evaluation_protocol_config.yaml").read_text()
                ),
                "model_knowledge_cutoff_policy_config": yaml.safe_load(
                    (root / "config/governance/model_knowledge_cutoff_policy.yaml").read_text()
                ),
            },
            {"execution_profile": "QUALIFICATION"},
        )
