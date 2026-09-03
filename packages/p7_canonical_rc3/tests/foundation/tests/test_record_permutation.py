from copy import deepcopy
import random

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02


def test_child_record_permutation_is_canonical(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    leg = next(row for row in artifacts if row["artifact_name"] == "strategy_leg_panel")
    second = deepcopy(leg["records"][0])
    second["leg_id"] = "leg-2"
    leg["records"].append(second)
    leg["record_count"] = 2
    base = {key: value for key, value in leg.items() if key != "content_sha256"}
    leg["content_sha256"] = content_sha256(base)
    ref = next(row for row in manifest["artifacts"] if row["artifact_name"] == "strategy_leg_panel")
    ref["content_sha256"] = leg["content_sha256"]
    ref["record_count"] = 2

    expected = None
    for seed in range(20):
        random.Random(seed).shuffle(leg["records"])
        base = {key: value for key, value in leg.items() if key != "content_sha256"}
        leg["content_sha256"] = content_sha256(base)
        ref["content_sha256"] = leg["content_sha256"]
        index = run_m01(
            {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
            module_config,
        )["outputs"]["verified_p6_artifact_index"]
        records = run_m02({"verified_p6_artifact_index": index}, module_config)["outputs"]["validated_strategy_candidate_bundle"]["records"]
        leg_ids = [row["leg_id"] for row in records[0]["legs"]]
        expected = leg_ids if expected is None else expected
        assert leg_ids == expected
