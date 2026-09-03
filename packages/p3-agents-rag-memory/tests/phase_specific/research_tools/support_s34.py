from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from .support import load_yaml
from .support_s33 import DECISION_TIME, build_s33_m01, s32_outputs
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s34 import (
    build_capability_taxonomy_contracts,
    build_context_tool_overlay,
    build_effective_entitlements,
    build_person_research_profiles,
    build_research_plan_templates,
)


def person_schema_policy() -> dict[str, Any]:
    return load_yaml("config/resources/s15/person_schema_policy.yaml")


def person_inputs() -> dict[str, Any]:
    return {
        "person_seed_panel": {
            "artifact_id": "person-seed-panel",
            "records": [
                {"person_id": "retail-1", "person_seed": 101},
                {"person_id": "institutional-1", "person_seed": 202},
            ],
        },
        "validated_population_manifest": {
            "artifact_id": "population-manifest",
            "population_manifest": {
                "persons": [
                    {
                        "person_id": "retail-1",
                        "allowed_data_classes": ["PUBLIC", "REGULATORY", "MARKET_DELAYED", "MACRO_PUBLIC"],
                        "constraints": ["restricted_compute"],
                        "profile": {
                            "economic_role": "retail_investor",
                            "institution_type": "individual",
                            "capabilities": {
                                "research": 0.35,
                                "quantitative": 0.30,
                                "verbal": 0.45,
                                "coding": 0.10,
                                "tool_use": 0.30,
                            },
                            "resources": {
                                "research_time": 0.25,
                                "computational_access": 0.20,
                                "flags": ["public_data", "low_research_time", "limited_compute"],
                            },
                        },
                    },
                    {
                        "person_id": "institutional-1",
                        "allowed_data_classes": [
                            "PUBLIC", "REGULATORY", "MARKET_DELAYED", "MACRO_PUBLIC",
                            "PROFESSIONAL", "PREMIUM", "MARKET_REALTIME", "INSTITUTIONAL",
                        ],
                        "constraints": [],
                        "profile": {
                            "economic_role": "fundamental_analyst",
                            "institution_type": "asset_manager",
                            "capabilities": {
                                "research": 0.92,
                                "quantitative": 0.82,
                                "verbal": 0.88,
                                "coding": 0.55,
                                "tool_use": 0.88,
                            },
                            "resources": {
                                "research_time": 0.90,
                                "computational_access": 0.80,
                                "flags": [
                                    "public_data", "professional_data", "terminal_access",
                                    "high_research_time", "high_compute",
                                ],
                            },
                        },
                    },
                ]
            },
        },
    }


def run_snapshot() -> dict[str, Any]:
    return {
        "run_id": "run-s34",
        "cycle_id": "cycle-s34",
        "snapshot_id": "snapshot-s34",
        "decision_time": DECISION_TIME,
        "execution_mode": "BACKTEST",
        "content_hash": "1" * 64,
    }


@lru_cache(maxsize=1)
def build_s34_m01_cached() -> dict[str, Any]:
    base = s32_outputs()
    return build_capability_taxonomy_contracts({
        **base,
        "research_capability_taxonomy_config": load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml"),
        "person_schema_policy": person_schema_policy(),
    })


def build_s34_m01() -> dict[str, Any]:
    return deepcopy(build_s34_m01_cached())


@lru_cache(maxsize=1)
def build_s34_m02_cached() -> dict[str, Any]:
    return build_person_research_profiles({
        **person_inputs(),
        **build_s34_m01(),
        "person_schema_policy": person_schema_policy(),
        "capability_profile_policy_config": load_yaml("config/research_tools/CAPABILITY_PROFILE_POLICY.yaml"),
        "phase3_run_snapshot": run_snapshot(),
    })


def build_s34_m02(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not overrides:
        return deepcopy(build_s34_m02_cached())
    inputs = {
        **person_inputs(), **build_s34_m01(),
        "person_schema_policy": person_schema_policy(),
        "capability_profile_policy_config": load_yaml("config/research_tools/CAPABILITY_PROFILE_POLICY.yaml"),
        "phase3_run_snapshot": run_snapshot(),
    }
    inputs.update(overrides)
    return build_person_research_profiles(inputs)


@lru_cache(maxsize=1)
def build_s34_m03_cached() -> dict[str, Any]:
    m01 = build_s34_m01()
    s33_m01 = build_s33_m01()
    return build_research_plan_templates({
        **s32_outputs(), **m01, **s33_m01,
        "research_plan_registry_config": load_yaml("config/research_tools/RESEARCH_PLAN_REGISTRY.yaml"),
    })


def build_s34_m03(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not overrides:
        return deepcopy(build_s34_m03_cached())
    inputs = {
        **s32_outputs(), **build_s34_m01(), **build_s33_m01(),
        "research_plan_registry_config": load_yaml("config/research_tools/RESEARCH_PLAN_REGISTRY.yaml"),
    }
    inputs.update(overrides)
    return build_research_plan_templates(inputs)


def legacy_entitlements() -> dict[str, Any]:
    return {
        "artifact_id": "legacy-entitlements",
        "records": [
            {"person_id": "retail-1", "tool_id": "research.search_filings.v1", "decision": "ALLOW", "budget_calls_per_cycle": 3},
            {"person_id": "institutional-1", "tool_id": "research.search_filings.v1", "decision": "ALLOW", "budget_calls_per_cycle": 5},
        ],
    }


def gateway_policy() -> dict[str, Any]:
    return {
        "schema_version": "p3.s21.v1",
        "policy_version": "1.0.0",
        "pit_required": True,
        "audit_required": True,
        "cache_mode": "frozen_in_backtest",
        "cognition_default_calls_per_person_cycle": 5,
        "hard_limit_calls_per_person_cycle": 5,
        "credential_policy": "handle_only",
        "timeout_seconds": 30.0,
        "max_retry_attempts": 1,
        "retry_backoff_seconds": 0.1,
        "provider_failure_policy": "material_no_fake_success",
    }


@lru_cache(maxsize=1)
def build_s34_m04_cached() -> dict[str, Any]:
    return build_effective_entitlements({
        **s32_outputs(), **build_s33_m01(), **build_s34_m02(), **build_s34_m03(),
        "person_tool_entitlement_panel": legacy_entitlements(),
        "research_entitlement_policy_config": load_yaml("config/research_tools/RESEARCH_ENTITLEMENT_POLICY.yaml"),
        "mcp_gateway_policy": gateway_policy(),
        "phase3_run_snapshot": run_snapshot(),
    })


def build_s34_m04(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not overrides:
        return deepcopy(build_s34_m04_cached())
    inputs = {
        **s32_outputs(), **build_s33_m01(), **build_s34_m02(), **build_s34_m03(),
        "person_tool_entitlement_panel": legacy_entitlements(),
        "research_entitlement_policy_config": load_yaml("config/research_tools/RESEARCH_ENTITLEMENT_POLICY.yaml"),
        "mcp_gateway_policy": gateway_policy(),
        "phase3_run_snapshot": run_snapshot(),
    }
    inputs.update(overrides)
    return build_effective_entitlements(inputs)


def s20_context_bundle() -> dict[str, Any]:
    sections = [
        {"section_type": "PERSON_IDENTITY", "content": "Analytical evidence-seeking investor."},
        {"section_type": "PRIOR_BELIEFS", "content": "Neutral prior belief."},
        {"section_type": "RETRIEVED_EVIDENCE", "content": "Public evidence available.", "evidence_refs": ["ev-public-1"]},
    ]
    return {
        "run_id": "run-s34",
        "cycle_id": "cycle-s34",
        "records": [
            {
                "context": {
                    "context_id": "ctx-retail-1", "person_id": "retail-1",
                    "activation_id": "act-retail-1", "as_of": DECISION_TIME,
                    "sections": sections,
                },
                "budget_report": {"effective_budget": 2600},
            },
            {
                "context": {
                    "context_id": "ctx-institutional-1", "person_id": "institutional-1",
                    "activation_id": "act-institutional-1", "as_of": DECISION_TIME,
                    "sections": sections,
                },
                "budget_report": {"effective_budget": 5200},
            },
        ],
        "content_hash": "2" * 64,
        "status": "READY",
    }


def cognition_config() -> dict[str, Any]:
    return {
        "schema_version": "p3.s21.v1",
        "temperature": 0.1,
        "structured_output": True,
        "max_tool_calls_per_cycle": 5,
        "max_repair_attempts": 1,
        "no_trade_authority": True,
        "initial_prompt_id": "p3.s21.initial",
        "initial_prompt_version": "1.0.0",
        "continuation_prompt_id": "p3.s21.continuation",
        "continuation_prompt_version": "1.0.0",
    }


@lru_cache(maxsize=1)
def build_s34_m05_cached() -> dict[str, Any]:
    return build_context_tool_overlay({
        **s32_outputs(), **build_s34_m01(), **build_s34_m02(), **build_s34_m03(), **build_s34_m04(),
        **person_inputs(),
        "validated_person_context_bundle": s20_context_bundle(),
        "phase3_run_snapshot": run_snapshot(),
        "cognition_config": cognition_config(),
        "context_tool_descriptor_policy_config": load_yaml("config/research_tools/CONTEXT_TOOL_DESCRIPTOR_POLICY.yaml"),
    })


def build_s34_m05(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if not overrides:
        return deepcopy(build_s34_m05_cached())
    inputs = {
        **s32_outputs(), **build_s34_m01(), **build_s34_m02(), **build_s34_m03(), **build_s34_m04(), **person_inputs(),
        "validated_person_context_bundle": s20_context_bundle(),
        "phase3_run_snapshot": run_snapshot(),
        "cognition_config": cognition_config(),
        "context_tool_descriptor_policy_config": load_yaml("config/research_tools/CONTEXT_TOOL_DESCRIPTOR_POLICY.yaml"),
    }
    inputs.update(overrides)
    return build_context_tool_overlay(inputs)
