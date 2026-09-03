from copy import deepcopy
import random

from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02


def test_artifact_permutation_does_not_change_candidate_bundle(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    baseline_index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    baseline = run_m02({"verified_p6_artifact_index": baseline_index}, module_config)
    for seed in range(20):
        shuffled = deepcopy(artifacts)
        random.Random(seed).shuffle(shuffled)
        index = run_m01(
            {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": shuffled},
            module_config,
        )["outputs"]["verified_p6_artifact_index"]
        result = run_m02({"verified_p6_artifact_index": index}, module_config)
        assert result["outputs"]["validated_strategy_candidate_bundle"]["records"] == baseline["outputs"]["validated_strategy_candidate_bundle"]["records"]


def test_replay_is_deterministic(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    first = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )
    second = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )
    assert first == second
