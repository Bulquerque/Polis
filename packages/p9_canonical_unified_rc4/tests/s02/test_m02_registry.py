from __future__ import annotations

import json

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.experiment import ExperimentValidationInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.parameters import HyperparameterRegistryInput
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m01_experiment_validator import ExperimentSpecificationValidator
from quant_pipeline.phase_09.subphases.s02_experiment_governance.m02_parameter_registry import HyperparameterSchemaRegistry
from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.base import RegistryState


def validated(s2_request):
    out = ExperimentSpecificationValidator().validate(ExperimentValidationInput(
        specification=s2_request.specification,
        frozen_cohort=s2_request.s1_outputs.frozen_cohort,
        metric_registry=s2_request.metric_registry,
        capability_registry=s2_request.capability_registry,
        promotion_policy=s2_request.promotion_policy,
    ))
    assert out.validated is not None
    return out.validated


def test_registry_contains_public_p5_to_p8_parameters(s2_request) -> None:
    out = HyperparameterSchemaRegistry().build(HyperparameterRegistryInput(
        validated_specification=validated(s2_request),
        phase_contracts=s2_request.phase_parameter_contracts,
        deprecations=s2_request.deprecation_registry,
    ))
    assert out.snapshot is not None
    assert out.compatibility_report.state is RegistryState.REGISTRY_SNAPSHOT_READY
    assert len(out.snapshot.definitions) == 6
    assert out.authority_map is not None


def test_missing_phase_contract_is_blocking(s2_request) -> None:
    raw = s2_request.phase_parameter_contracts.model_dump(mode="json")
    raw["snapshots"] = tuple(s for s in raw["snapshots"] if s["phase_id"] != "P6")
    contracts = type(s2_request.phase_parameter_contracts).model_validate_json(json.dumps(raw))
    out = HyperparameterSchemaRegistry().build(HyperparameterRegistryInput(
        validated_specification=validated(s2_request), phase_contracts=contracts,
        deprecations=s2_request.deprecation_registry,
    ))
    assert out.snapshot is None
    assert any(i.reason_code == "P9_S2_PARAMETER_CONTRACT_MISSING" for i in out.compatibility_report.issues)


def test_ambiguous_alias_is_blocking(s2_request) -> None:
    raw = s2_request.phase_parameter_contracts.model_dump(mode="json")
    raw["snapshots"][0]["parameters"][0]["aliases"] = ["P8.legacy.shared"]
    raw["snapshots"][1]["parameters"][0]["aliases"] = ["P8.legacy.shared"]
    contracts = type(s2_request.phase_parameter_contracts).model_validate_json(json.dumps(raw))
    out = HyperparameterSchemaRegistry().build(HyperparameterRegistryInput(
        validated_specification=validated(s2_request), phase_contracts=contracts,
        deprecations=s2_request.deprecation_registry,
    ))
    assert out.snapshot is None
    assert any(i.reason_code == "P9_S2_PARAMETER_ALIAS_AMBIGUOUS" for i in out.compatibility_report.issues)
