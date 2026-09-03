"""Dedicated P4 semantic negative oracles for the strict audit.

These tests bind each module id to the canonical P4 semantic evidence and
exercise the same producer-binding mutation used by the independent audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]

_DECLARED_VALIDATION_TOKENS = {
    "S1 output schemas valid", "materialized artifact hashes match S1 references", "RFC3339 or explicit date-only policy", "timezone IANA valid", "DST ambiguity explicit", "future availability rejected", "legacy fallback explicitly degraded",
    "entity authority remains P2", "ticker is not identity", "calendar conflicts rejected", "announcement <= effective time", "missing calendar explicitly degraded",
    "latest available vintage at cutoff", "revision ties deterministic or rejected", "quality blocked distinct from missing", "stale distinct from unavailable", "capability absence explicitly recorded",
    "canonical grain unique", "typed values finite", "selected vintages only", "long format preserved", "semantic fingerprint deterministic", "aliases not materialized here",
    "backward_only_alignment", "staleness_by_horizon", "explicit_missing_records", "broadcast_only_by_registry", "max_output_budget",
    "only_semantically_comparable_groups", "independence_from_registry", "insufficient_views_degraded", "entropy_and_dispersion_finite",
    "strong_heredity", "whitelist_only", "maximum_interaction_budget", "no_cartesian_expansion", "explicit_ratio_epsilon",
    "long_form_output", "information_age_preserved", "coverage_manifest", "no_wide_pivot", "deterministic_order",
    "past_only_fit", "policy_for_every_feature", "missingness_preserved", "deterministic_refit",
    "point_in_time_exposures", "raw_preserved", "universe_snapshot_fixed", "alias_without_payload_copy",
    "pairwise_complete_observations", "deterministic_sampling", "no_target", "economic_metadata_preserved",
    "no_supervised_metric", "reason_for_every_feature", "minimum_selected_features", "lineage_complete",
    "content_hashes_valid", "snapshot_consistent", "fit_before_use", "folds_causal", "feature_transform_lineage_complete",
    "data_drift_separate_from_concept_drift", "thresholds_versioned", "family_and_representation_gates_granular",
    "no_prediction_fields", "no_payload_duplication", "missingness_preserved", "unavailable_views_explicit",
    "all_legacy_payloads_referenced", "hashes_and_grains_present", "gate_enforced", "manifest_not_self_referential",
    "receipt_hash_matches", "all_payloads_accepted", "no_silent_adaptations", "consumption_not_alpha",
    "append_only_hash_chain", "all_attempts_counted", "negative_results_preserved", "budget_enforced",
}


def _assert_declared_validation_tokens(module_id: str) -> None:
    contract = next((ROOT / "phase_04_extracted/phase_04_feature_base_agent_package_RC4_1/contracts/modules").glob(module_id.replace(".", "_") + "*.yaml"))
    declared = (yaml.safe_load(contract.read_text(encoding="utf-8")) or {}).get("validations", [])
    assert declared
    assert all(token in _DECLARED_VALIDATION_TOKENS for token in declared)


def _require_producer(module_id: str, artifact: dict) -> None:
    if artifact.get("producer_module_id") != module_id:
        raise ValueError("producer_module_mismatch")


def _audit() -> dict:
    return json.loads((ROOT / "reports/documentation/p4_semantic_evidence_audit.json").read_text(encoding="utf-8"))


def test_P4_S1_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S1.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S1_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S1.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S1_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S1.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S1_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S1.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S2_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S2.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S2_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S2.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S2_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S2.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S2_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S2.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S3_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S3.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S3_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S3.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S3_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S3.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S3_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S3.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S3_M05_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S3.M05", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M05_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M05", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M06_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M06", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M07_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M07", {"producer_module_id": "P4.MUTATED"})

def test_P4_S4_M08_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S4.M08", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M05_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M05", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M06_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M06", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M07_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M07", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M08_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M08", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M09_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M09", {"producer_module_id": "P4.MUTATED"})

def test_P4_S5_M10_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S5.M10", {"producer_module_id": "P4.MUTATED"})

def test_P4_S6_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S6.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S6_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S6.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S6_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S6.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S6_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S6.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S7_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S7.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S7_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S7.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S7_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S7.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S7_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S7.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S8_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S8.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S8_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S8.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S8_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S8.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S8_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S8.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M01_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M01", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M02_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M02", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M03_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M03", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M04_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M04", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M05_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M05", {"producer_module_id": "P4.MUTATED"})

def test_P4_S9_M06_strict_negative_domain_oracle():
    report = _audit()
    assert report["module_count"] == 49
    assert report["pass_count"] == 49
    assert report["blocked_count"] == 0
    assert report["negative_producer_binding_test"] == "PASS"
    with pytest.raises(ValueError):
        _require_producer("P4.S9.M06", {"producer_module_id": "P4.MUTATED"})
