from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from phase_04_extracted.phase_04_feature_base_agent_package_RC4_1.tests.full_pipeline_fixture import build_full_inputs
from quant_pipeline.phase_04_feature_base.errors import BoundaryContractError
from quant_pipeline.phase_04_feature_base.integrated_runner import (
    run_foundation_and_governance,
    run_foundation_to_fusion,
)
from quant_pipeline.phase_04_feature_base.s9.drift import _distribution_metrics, _loading_drift
from quant_pipeline.phase_04_feature_base.runtime.artifact_envelope import RuntimeExecutionContext, build_artifact
from quant_pipeline.phase_04_feature_base.adapters.policies import build_s9_policy
from quant_pipeline.phase_04_feature_base.s9.records import DriftPolicy


def test_optional_p2_artifact_must_be_declared_in_manifest() -> None:
    inputs, context = build_full_inputs(24)
    broken = deepcopy(inputs)
    manifest = broken["phase4_handoff_manifest"]
    name = "clean_option_quotes_panel"
    artifact_id = broken[name]["artifact_id"]
    manifest["artifact_ids"] = [value for value in manifest["artifact_ids"] if value != artifact_id]
    manifest["artifact_refs"] = [
        reference
        for reference in manifest["artifact_refs"]
        if reference["artifact_name"] != name
    ]
    with pytest.raises(BoundaryContractError):
        run_foundation_and_governance(broken, context)


def test_empty_p2_artifacts_are_not_reported_available() -> None:
    inputs, context = build_full_inputs(24)
    result = run_foundation_and_governance(inputs, context)
    records = result["outputs"]["phase2_capability_matrix"]["records"]
    by_name = {record["artifact_name"]: record for record in records}
    assert by_name["clean_corporate_actions_panel"]["status"] == "UNAVAILABLE_UPSTREAM"
    assert by_name["clean_underlying_panel"]["status"] == "AVAILABLE"


def test_s3_compiles_plans_without_duplicate_materialization() -> None:
    inputs, context = build_full_inputs(24)
    result = run_foundation_and_governance(inputs, context)
    outputs = result["outputs"]
    assert outputs["causal_operator_execution_plan"]["records"]
    assert outputs["relational_operator_execution_plan"]["records"]
    assert outputs["causal_operator_result_panel"]["records"] == []
    assert outputs["relational_operator_result_panel"]["records"] == []
    assert outputs["causal_operator_result_panel"]["execution_status"] == "SKIPPED_STANDARD_BUILD"


def test_n_plus_one_proposal_is_closed_without_automatic_promotion() -> None:
    inputs, base_context = build_full_inputs(24)
    source_cycle = "cycle-integrated-23"
    context = replace(
        base_context,
        prior_cycle_ids=(source_cycle,),
        variable_evolution_source_cycle_id=source_cycle,
    )
    inputs["variable_evolution_input_manifest"] = {
        "manifest_id": "variable-evolution-fixture",
        "canonical_society_state_ref": "artifact://society-state",
        "social_feature_ref": "artifact://social-features",
        "context_memory_feature_ref": "artifact://context-memory",
        "hypothesis_registry_ref": "artifact://hypotheses",
        "belief_commitment_ref": "artifact://beliefs",
        "as_of_time": "2024-01-01T00:00:00Z",
        "lineage_id": "lineage-variable-evolution",
    }
    result = run_foundation_and_governance(inputs, context)
    decisions = result["outputs"]["observer_change_decision_registry"]["records"]
    assert decisions
    assert {record["decision"] for record in decisions} <= {"DEFER", "REJECT", "DUPLICATE"}
    assert all(record["automatic_promotion"] is False for record in decisions)


def test_wasserstein_requires_distributional_evidence() -> None:
    policy = DriftPolicy(
        reference_timestamps=20,
        current_timestamps=10,
        min_samples=8,
        ks_warn=0.35,
        ks_block=0.60,
        ks_significance_alpha=0.05,
        normalized_wasserstein_warn=0.75,
        normalized_wasserstein_block=2.0,
        missingness_delta_warn=0.15,
        missingness_delta_block=0.30,
        loading_drift_warn=0.25,
        loading_drift_block=0.50,
        reconstruction_delta_warn=0.25,
        reconstruction_delta_block=0.75,
        reconstruction_error_floor=0.05,
    )
    reference = np.asarray([0.0, 0.0, 0.0, 1.0] * 8, dtype=float)
    current = np.asarray([0.0, 0.0, 1.0, 0.0] * 8, dtype=float)
    _, pvalue, distance, severity = _distribution_metrics(reference, current, policy)
    assert pvalue is not None and pvalue > policy.ks_significance_alpha
    assert distance is not None
    assert severity == "PASS"

    shifted = np.asarray([2.0, 2.0, 2.0, 3.0] * 8, dtype=float)
    _, pvalue, _, severity = _distribution_metrics(reference, shifted, policy)
    assert pvalue is not None and pvalue <= policy.ks_significance_alpha
    assert severity == "BLOCK"


def test_loading_drift_compares_subspaces_when_component_count_changes() -> None:
    policy = DriftPolicy(
        reference_timestamps=20, current_timestamps=10, min_samples=8,
        ks_warn=0.35, ks_block=0.60, ks_significance_alpha=0.05,
        normalized_wasserstein_warn=0.75, normalized_wasserstein_block=2.0,
        missingness_delta_warn=0.15, missingness_delta_block=0.30,
        loading_drift_warn=0.25, loading_drift_block=0.50,
        reconstruction_delta_warn=0.25, reconstruction_delta_block=0.75,
        reconstruction_error_floor=0.05,
    )
    context = RuntimeExecutionContext(
        run_id="run", cycle_id="cycle", as_of_time="2026-08-06T00:00:00Z",
        created_at="2026-08-06T00:00:00Z", pipeline_version="test",
    )
    common = {
        "family_id": "F02", "horizon_group": "SHORT", "representation_type": "PCA",
    }
    states = build_artifact(
        artifact_name="pca_fit_state_manifest", schema_version="test", producer_module_id="test",
        context=context, grain=("fit_state_id",), lineage_id="test",
        records=[
            {**common, "fit_end": "2025-01-01", "components": [[1, 0, 0], [0, 1, 0]]},
            {**common, "fit_end": "2026-01-01", "components": [[-1, 0, 0]]},
        ],
    )
    assert _loading_drift(states, policy)[0]["loading_drift"] == pytest.approx(0.0)


def test_s9_capability_profile_can_reduce_required_families_explicitly() -> None:
    context = RuntimeExecutionContext(
        run_id="run", cycle_id="cycle", as_of_time="2026-08-06T00:00:00Z",
        created_at="2026-08-06T00:00:00Z", pipeline_version="test",
    )
    policy = build_s9_policy(
        context=context,
        overrides={"required_family_ids": ["F01", "F02", "F05"]},
    )
    assert policy.records[0]["family_coverage"]["required_family_ids"] == ["F01", "F02", "F05"]
    assert policy.metadata["policy_override"]["mode"] == "USER_APPROVED_CAPABILITY_PROFILE"
