from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module


def test_validates_complete_handoff(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    result = run_module(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )
    assert result["status"] == "PASS"
    assert result["outputs"]["verified_p6_artifact_index"]["record_count"] == 1


def test_rejects_hash_mismatch(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    artifacts[0]["records"][0]["underlying_id"] = "MUTATED"
    with pytest.raises(P7S1Error) as exc_info:
        run_module(
            {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
            module_config,
        )
    assert exc_info.value.code == "P7_P6_HASH_MISMATCH"


def test_rejects_undeclared_artifact(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    extra = deepcopy(artifacts[0])
    extra["artifact_name"] = "phantom_panel"
    extra["artifact_id"] = "phantom:1"
    artifacts.append(extra)
    with pytest.raises(P7S1Error) as exc_info:
        run_module(
            {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
            module_config,
        )
    assert exc_info.value.code == "P7_P6_ARTIFACT_UNDECLARED"
