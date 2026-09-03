from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M03_temporal_integrity_and_forbidden_field_firewall import run_module as run_m03


def candidate_bundle(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    return run_m02({"verified_p6_artifact_index": index}, module_config)["outputs"]["validated_strategy_candidate_bundle"]


def test_accepts_point_in_time_bundle(p6_fixture, module_config):
    bundle = candidate_bundle(p6_fixture, module_config)
    result = run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert result["outputs"]["temporally_safe_candidate_bundle"]["record_count"] == 1


def test_rejects_nested_forbidden_field(p6_fixture, module_config):
    bundle = candidate_bundle(p6_fixture, module_config)
    bundle["records"][0]["candidate"]["metadata"] = {"nested": [{"future_return": 9.0}]}
    with pytest.raises(P7S1Error) as exc_info:
        run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert exc_info.value.code == "P7_FORBIDDEN_FIELD"


def test_rejects_future_model_timestamp(p6_fixture, module_config):
    bundle = candidate_bundle(p6_fixture, module_config)
    bundle["records"][0]["candidate"]["model_trained_at"] = "2026-01-06T00:00:00Z"
    with pytest.raises(P7S1Error) as exc_info:
        run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert exc_info.value.code == "P7_MODEL_AFTER_DECISION"


def test_does_not_mutate_input(p6_fixture, module_config):
    bundle = candidate_bundle(p6_fixture, module_config)
    before = deepcopy(bundle)
    run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert bundle == before
