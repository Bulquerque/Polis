from copy import deepcopy

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02


def verified_index(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    return run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]


def test_reconstructs_complete_candidate(p6_fixture, module_config):
    result = run_m02({"verified_p6_artifact_index": verified_index(p6_fixture, module_config)}, module_config)
    records = result["outputs"]["validated_strategy_candidate_bundle"]["records"]
    assert len(records) == 1
    assert records[0]["candidate_id"] == "cand-1"
    assert len(records[0]["legs"]) == 1


def test_rejects_orphan_child(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    leg = next(item for item in artifacts if item["artifact_name"] == "strategy_leg_panel")
    leg["records"][0]["candidate_id"] = "unknown"
    from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
    base = {key: value for key, value in leg.items() if key != "content_sha256"}
    leg["content_sha256"] = content_sha256(base)
    ref = next(item for item in manifest["artifacts"] if item["artifact_name"] == "strategy_leg_panel")
    ref["content_sha256"] = leg["content_sha256"]
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc_info:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc_info.value.code == "P7_ORPHAN_CHILD_RECORD"
