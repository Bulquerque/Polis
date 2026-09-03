"""Deterministic fixtures shared by P3.S27 tests."""
from __future__ import annotations

from copy import deepcopy

CONTEXT = {
    "schema_version": "fixture.v1",
    "run_id": "run-s27-001",
    "cycle_id": 7,
    "as_of_time": "2026-06-10T00:00:00Z",
    "lineage_id": "lin-fixture-root",
}

CONFIG = {
    "version": "v1",
    "formula_version": "p3.s27.formulas.v1",
    "bearish_threshold": -0.1,
    "bullish_threshold": 0.1,
    "reversal_epsilon": 0.05,
    "velocity_min_elapsed_seconds": 60.0,
    "attention_formula": "weighted_mean_and_one_minus_normalized_entropy",
    "information_formula": "weighted_population_standard_deviation",
    "information_access_weight": 0.4,
    "research_depth_weight": 0.3,
    "validated_tool_weight": 0.3,
    "validated_tool_gain_cap": 1.0,
    "causal_delivery_statuses": ["SEEN", "INTERPRETED", "USED"],
    "validated_tool_statuses": ["SUCCEEDED", "VALIDATED"],
    "secondary_activation_reasons": ["SOCIAL_MESSAGE", "SOCIAL_TOOL"],
    "influence_concentration_formula": "HHI",
    "zero_coverage_policy": "MATERIAL_RECORD",
    "reject_causal_cycles": True,
}

PROPOSITIONS = {
    "version": "v1",
    "propositions": [
        {"proposition_id": "directional_outlook", "description": "direction", "allowed_horizons": ["5d", "21d"]},
        {"proposition_id": "volatility_outlook", "description": "volatility", "allowed_horizons": ["5d"]},
    ],
}

POPULATION = {
    **CONTEXT,
    "lineage_id": "lin-population",
    "records": [
        {"person_id": "p1", "representation_weight": 1.0, "role": "expert", "institution_type": "bank", "lineage_id": "lin-p1"},
        {"person_id": "p2", "representation_weight": 2.0, "role": "retail", "institution_type": "individual", "lineage_id": "lin-p2"},
        {"person_id": "p3", "representation_weight": 1.0, "role": "analyst", "institution_type": "research", "lineage_id": "lin-p3"},
    ],
}

BELIEFS = {
    **CONTEXT,
    "lineage_id": "lin-beliefs",
    "records": [
        {"person_id": "p1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "prior_value": -0.4, "new_value": 0.6, "delta": 1.0, "confidence": 0.8, "uncertainty": 0.2, "prior_updated_at": "2026-06-08T00:00:00Z", "changed_at": "2026-06-09T00:00:00Z", "commitment_id": "c1", "evidence_refs": ["e1"], "lineage_id": "lin-1"},
        {"person_id": "p2", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "prior_value": 0.5, "new_value": -0.5, "delta": -1.0, "confidence": 0.5, "uncertainty": 0.5, "prior_updated_at": "2026-06-07T00:00:00Z", "changed_at": "2026-06-09T00:00:00Z", "commitment_id": "c2", "evidence_refs": ["e2"], "lineage_id": "lin-2"},
        {"person_id": "p3", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "prior_value": 0.0, "new_value": 0.0, "delta": 0.0, "confidence": 1.0, "uncertainty": 0.1, "prior_updated_at": None, "changed_at": "2026-06-09T00:00:00Z", "commitment_id": "c3", "evidence_refs": ["e3"], "lineage_id": "lin-3"},
    ],
}

STIMULI = {
    **CONTEXT,
    "lineage_id": "lin-stimuli",
    "records": [
        {"stimulus_id": "s1", "origin": "EXTERNAL", "source_event_id": "ev1", "causal_parent_id": None, "target_person_id": None, "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "created_cycle": 7, "target_cycle": 7, "event_time": "2026-06-09T00:00:00Z", "available_at": "2026-06-09T00:00:00Z", "evidence_refs": ["e1"], "lineage_id": "lin-s1"},
        {"stimulus_id": "s2", "origin": "EXTERNAL", "source_event_id": "ev2", "causal_parent_id": None, "target_person_id": None, "underlying_id": "VALE3", "proposition_id": "directional_outlook", "horizon": "5d", "created_cycle": 7, "target_cycle": 7, "event_time": "2026-06-09T00:30:00Z", "available_at": "2026-06-09T00:30:00Z", "evidence_refs": ["e4"], "lineage_id": "lin-s2"},
    ],
}

PERSON_STATES = {
    **CONTEXT,
    "lineage_id": "lin-person-states",
    "records": [
        {"person_id": "p1", "emergence_states": [{"underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "attention_score": 0.9, "information_access_score": 0.8, "research_depth": 0.7, "updated_at": "2026-06-09T20:00:00Z", "lineage_id": "lin-es1"}]},
        {"person_id": "p2", "emergence_states": [{"underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "attention_score": 0.3, "information_access_score": 0.2, "research_depth": 0.3, "updated_at": "2026-06-09T20:00:00Z", "lineage_id": "lin-es2"}]},
        {"person_id": "p3", "emergence_states": [{"underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "attention_score": 0.0, "information_access_score": 0.1, "research_depth": 0.1, "updated_at": "2026-06-09T20:00:00Z", "lineage_id": "lin-es3"}]},
    ],
}

TOOL_AUDIT = {
    **CONTEXT,
    "lineage_id": "lin-tools",
    "records": [
        {"call_id": "tool1", "person_id": "p1", "tool_id": "search", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "execution_status": "VALIDATED", "result_validated": True, "executed_at": "2026-06-09T21:00:00Z", "information_gain": 0.6, "research_depth": 0.6, "evidence_refs": ["e5"], "lineage_id": "lin-tool1"},
        {"call_id": "tool2", "person_id": "p2", "tool_id": "search", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "execution_status": "AUTHORIZED", "result_validated": False, "executed_at": "2026-06-09T21:00:00Z", "information_gain": 1.0, "research_depth": 1.0, "evidence_refs": ["e6"], "lineage_id": "lin-tool2"},
    ],
}

ENTITLEMENTS = {
    **CONTEXT,
    "lineage_id": "lin-entitlements",
    "records": [
        {"person_id": "p1", "tool_id": "search", "entitled": True, "lineage_id": "lin-ent1"},
        {"person_id": "p2", "tool_id": "search", "entitled": True, "lineage_id": "lin-ent2"},
        {"person_id": "p3", "tool_id": "search", "entitled": False, "lineage_id": "lin-ent3"},
    ],
}

ACTIVATIONS = {
    **CONTEXT,
    "lineage_id": "lin-activations",
    "records": [
        {"activation_id": "a1", "person_id": "p1", "stimulus_id": "s1", "activation_reason": "EXTERNAL", "activation_score": 0.9, "threshold": 0.5, "scheduled_at": "2026-06-09T01:00:00Z", "causal_parent_id": "s1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "lineage_id": "lin-a1"},
        {"activation_id": "a2", "person_id": "p2", "stimulus_id": "s1", "activation_reason": "SOCIAL_MESSAGE", "activation_score": 0.8, "threshold": 0.5, "scheduled_at": "2026-06-09T03:00:00Z", "causal_parent_id": "m1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "lineage_id": "lin-a2"},
        {"activation_id": "a3", "person_id": "p3", "stimulus_id": "s1", "activation_reason": "SOCIAL_TOOL", "activation_score": 0.7, "threshold": 0.5, "scheduled_at": "2026-06-09T05:00:00Z", "causal_parent_id": "sta1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "lineage_id": "lin-a3"},
    ],
}

DELIVERIES = {
    **CONTEXT,
    "lineage_id": "lin-deliveries",
    "records": [
        {"message_id": "m1", "sender_person_id": "p1", "receiver_person_id": "p2", "status": "SEEN", "created_cycle": 7, "effective_cycle": 7, "created_at": "2026-06-09T01:15:00Z", "status_at": "2026-06-09T02:00:00Z", "causal_parent_id": "a1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "evidence_refs": ["e7"], "lineage_id": "lin-m1"},
        {"message_id": "m2", "sender_person_id": "p2", "receiver_person_id": "p3", "status": "INTERPRETED", "created_cycle": 7, "effective_cycle": 7, "created_at": "2026-06-09T03:15:00Z", "status_at": "2026-06-09T04:00:00Z", "causal_parent_id": "a2", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "evidence_refs": ["e8"], "lineage_id": "lin-m2"},
        {"message_id": "ignored", "sender_person_id": "p1", "receiver_person_id": "p3", "status": "DELIVERED", "created_cycle": 7, "effective_cycle": 7, "created_at": "2026-06-09T01:10:00Z", "status_at": "2026-06-09T01:20:00Z", "causal_parent_id": "a1", "underlying_id": "PETR4", "proposition_id": "directional_outlook", "horizon": "5d", "evidence_refs": ["e9"], "lineage_id": "lin-ignore"},
    ],
}

SOCIAL_TOOL_AUDIT = {
    **CONTEXT,
    "lineage_id": "lin-social-tools",
    "records": [
        {"audit_id": "sta1", "person_id": "p3", "message_id": "m2", "tool_call_id": "stc1", "execution_status": "VALIDATED", "result_validated": True, "event_time": "2026-06-09T04:30:00Z", "causal_parent_id": "m2", "evidence_refs": ["e10"], "lineage_id": "lin-sta1"}
    ],
}


def m01_inputs() -> dict:
    return deepcopy({"next_belief_state_panel": BELIEFS, "validated_population_manifest": POPULATION, "stimulus_panel": STIMULI, "proposition_registry_config": PROPOSITIONS, "aggregation_semantics_config": CONFIG})


def m02_inputs() -> dict:
    return deepcopy({"validated_next_person_state_panel": PERSON_STATES, "tool_call_audit_panel": TOOL_AUDIT, "person_tool_entitlement_panel": ENTITLEMENTS, "validated_population_manifest": POPULATION, "aggregation_semantics_config": CONFIG})


def m03_inputs() -> dict:
    return deepcopy({"activation_panel": ACTIVATIONS, "stimulus_panel": STIMULI, "social_delivery_panel": DELIVERIES, "social_tool_audit_panel": SOCIAL_TOOL_AUDIT, "aggregation_semantics_config": CONFIG})
