from __future__ import annotations

import json

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import (
    CapabilityState,
    ExperimentValidationState,
    SearchStrategy,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.experiment import (
    ExperimentValidationInput,
)
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m01_experiment_validator import (
    ExperimentSpecificationValidator,
)


def build_input(s2_request, **updates):
    data = {
        "specification": s2_request.specification,
        "frozen_cohort": s2_request.s1_outputs.frozen_cohort,
        "metric_registry": s2_request.metric_registry,
        "capability_registry": s2_request.capability_registry,
        "promotion_policy": s2_request.promotion_policy,
    }
    data.update(updates)
    return ExperimentValidationInput.model_validate(data)


def test_valid_specification_is_content_addressed(s2_request) -> None:
    out = ExperimentSpecificationValidator().validate(build_input(s2_request))
    assert out.report.state is ExperimentValidationState.SPEC_VALID
    assert out.validated is not None
    assert len(out.validated.specification_sha256) == 64


def test_holdout_overlap_is_blocked(s2_request) -> None:
    raw = s2_request.specification.model_dump(mode="json")
    raw["final_holdout_dataset_ids"] = s2_request.specification.development_dataset_ids
    spec = type(s2_request.specification).model_validate_json(json.dumps(raw))
    out = ExperimentSpecificationValidator().validate(build_input(s2_request, specification=spec))
    assert out.validated is None
    assert out.report.state is ExperimentValidationState.HOLDOUT_POLICY_INVALID
    assert "P9_S2_SPEC_HOLDOUT_LEAKAGE" in out.report.reason_codes


def test_unknown_metric_is_blocking(s2_request) -> None:
    raw = s2_request.specification.model_dump(mode="json")
    raw["primary_metric_id"] = "missing.metric"
    spec = type(s2_request.specification).model_validate_json(json.dumps(raw))
    out = ExperimentSpecificationValidator().validate(build_input(s2_request, specification=spec))
    assert out.validated is None
    assert "P9_S2_SPEC_METRIC_UNKNOWN" in out.report.reason_codes


def test_limited_capability_yields_limited_spec(s2_request) -> None:
    raw = s2_request.capability_registry.model_dump(mode="json")
    raw["capabilities"][0]["state"] = CapabilityState.LIMITED
    raw["capabilities"][0]["limitation"] = "capacity limited"
    registry = type(s2_request.capability_registry).model_validate_json(json.dumps(raw))
    out = ExperimentSpecificationValidator().validate(build_input(s2_request, capability_registry=registry))
    assert out.validated is not None
    assert out.report.state is ExperimentValidationState.SPEC_VALID_WITH_LIMITATIONS


def test_bohb_is_explicitly_unavailable(s2_request) -> None:
    raw = s2_request.specification.model_dump(mode="json")
    raw["search_strategy"] = SearchStrategy.BOHB
    spec = type(s2_request.specification).model_validate_json(json.dumps(raw))
    out = ExperimentSpecificationValidator().validate(build_input(s2_request, specification=spec))
    assert out.validated is None
    assert out.report.state is ExperimentValidationState.CAPABILITY_UNAVAILABLE
    assert "P9_S2_SPEC_BOHB_CAPABILITY_RESERVED" in out.report.reason_codes
