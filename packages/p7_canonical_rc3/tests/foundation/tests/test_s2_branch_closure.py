from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_07_strategy_tournament.foundation.s2_comparability.common import (
    finite_number,
    first_path,
    get_path,
    parse_aware_datetime,
    source_artifact_for_path,
)
from quant_pipeline.phase_07_strategy_tournament.foundation.s2_comparability.models import (
    FoundationHandoffRecord,
    ComparisonGroupPolicyRegistry,
    EligibilityPolicy,
    EligibilityPolicyRegistry,
    HandoffArtifactReference,
    MetricDefinition,
    MetricSemanticsRegistry,
    ObjectiveFamilyDefinition,
    ObjectiveFamilyRegistry,
    RiskBucket,
)


def test_common_path_and_scalar_edges():
    payload = {"a": {"b": None}, "x": {"y": 2}}
    assert get_path(payload, "missing", 7) == 7
    with pytest.raises(KeyError):
        get_path(payload, "missing")
    assert first_path(payload, ("a.b", "x.y")) == ("x.y", 2)
    assert first_path(payload, ("a.b", "none")) is None
    assert finite_number(True) is None
    assert finite_number(float("nan")) is None
    assert source_artifact_for_path("unknown.value") == "validated_strategy_candidate_bundle"


def test_datetime_parser_edges():
    aware = parse_aware_datetime("2026-01-05T14:30:00Z")
    assert aware.utcoffset() is not None
    assert parse_aware_datetime(aware) == aware
    with pytest.raises(TypeError):
        parse_aware_datetime(1)
    with pytest.raises(ValueError):
        parse_aware_datetime(datetime(2026, 1, 5, 14, 30))


def _eligibility_policy(**updates):
    base = {
        "policy_id": "eligibility-v1",
        "version": "1.0.0",
        "allowed_objective_families": ["RANGE"],
    }
    base.update(updates)
    return base


def test_eligibility_policy_rejects_duplicate_objectives():
    with pytest.raises(ValidationError):
        EligibilityPolicy.model_validate(
            _eligibility_policy(allowed_objective_families=["RANGE", "RANGE"])
        )


def test_eligibility_registry_rejects_duplicate_and_missing_active():
    policy = _eligibility_policy()
    with pytest.raises(ValidationError):
        EligibilityPolicyRegistry.model_validate(
            {
                "registry_id": "r",
                "registry_version": "1.0.0",
                "active_policy_id": "eligibility-v1",
                "policies": [policy, policy],
            }
        )
    with pytest.raises(ValidationError):
        EligibilityPolicyRegistry.model_validate(
            {
                "registry_id": "r",
                "registry_version": "1.0.0",
                "active_policy_id": "missing",
                "policies": [policy],
            }
        )


def test_risk_bucket_rejects_inverted_interval():
    with pytest.raises(ValidationError):
        RiskBucket.model_validate(
            {"bucket_id": "bad", "lower_inclusive": 10, "upper_exclusive": 5}
        )


def _comparison_registry(s2_registries):
    return deepcopy(s2_registries["comparison"])


def test_comparison_policy_rejects_wrong_dimensions(s2_registries):
    registry = _comparison_registry(s2_registries)
    registry["policies"][0]["dimensions"] = ["cycle_id"]
    with pytest.raises(ValidationError):
        ComparisonGroupPolicyRegistry.model_validate(registry)


def test_comparison_policy_rejects_empty_unordered_and_closed_tail(s2_registries):
    registry = _comparison_registry(s2_registries)
    registry["policies"][0]["risk_buckets"] = []
    with pytest.raises(ValidationError):
        ComparisonGroupPolicyRegistry.model_validate(registry)

    registry = _comparison_registry(s2_registries)
    registry["policies"][0]["risk_buckets"] = list(
        reversed(registry["policies"][0]["risk_buckets"])
    )
    with pytest.raises(ValidationError):
        ComparisonGroupPolicyRegistry.model_validate(registry)

    registry = _comparison_registry(s2_registries)
    registry["policies"][0]["risk_buckets"][-1]["upper_exclusive"] = 9999999
    with pytest.raises(ValidationError):
        ComparisonGroupPolicyRegistry.model_validate(registry)


def test_comparison_registry_rejects_duplicate_policies(s2_registries):
    registry = _comparison_registry(s2_registries)
    registry["policies"].append(deepcopy(registry["policies"][0]))
    with pytest.raises(ValidationError):
        ComparisonGroupPolicyRegistry.model_validate(registry)


def test_metric_models_reject_empty_paths_and_duplicate_ids(s2_registries):
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate(
            {
                "metric_id": "m",
                "semantic_version": "1.0.0",
                "source_paths": [],
                "units": "ratio",
                "direction": "MAXIMIZE",
            }
        )
    registry = deepcopy(s2_registries["metrics"])
    registry["metrics"].append(deepcopy(registry["metrics"][0]))
    with pytest.raises(ValidationError):
        MetricSemanticsRegistry.model_validate(registry)


def test_objective_models_reject_overlap_and_duplicate_families(s2_registries):
    with pytest.raises(ValidationError):
        ObjectiveFamilyDefinition.model_validate(
            {
                "objective_family": "RANGE",
                "required_metric_ids": ["m"],
                "optional_metric_ids": ["m"],
            }
        )
    registry = deepcopy(s2_registries["objectives"])
    registry["families"].append(deepcopy(registry["families"][0]))
    with pytest.raises(ValidationError):
        ObjectiveFamilyRegistry.model_validate(registry)


def test_handoff_model_rejects_duplicate_artifact_names():
    reference = HandoffArtifactReference(
        artifact_name="eligible_strategy_candidate_panel",
        artifact_id="artifact-1",
        content_sha256="0" * 64,
        schema_version="2.0.0",
        record_count=0,
        grain="one_record_per_candidate",
        producer_module_id="P7.S2.M01",
    )
    with pytest.raises(ValidationError):
        FoundationHandoffRecord(
            handoff_id="h",
            contract_version="2.0.0",
            semantic_version="2.0.0",
            producer_stage="FOUNDATION",
            consumer_stages=("TOURNAMENT",),
            artifacts=(reference, reference),
        )
