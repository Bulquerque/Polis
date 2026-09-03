import copy, random
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s5 import run_s5_pipeline


def _shuffle_artifact(artifact, seed):
    rng = random.Random(seed)
    rng.shuffle(artifact["records"])
    artifact["content_sha256"] = digest(artifact["records"])


def test_record_permutation_preserves_model_hashes(input_bundle, config):
    first = run_s5_pipeline(copy.deepcopy(input_bundle), copy.deepcopy(config))
    shuffled = copy.deepcopy(input_bundle)
    _shuffle_artifact(shuffled["historical_tournament_snapshots"], 1)
    _shuffle_artifact(shuffled["historical_candidate_counterfactual_outcome_panel"], 2)
    second = run_s5_pipeline(shuffled, copy.deepcopy(config))
    first_hashes = sorted(row["model_hash"] for row in first["outputs"]["ltr_model_artifact"]["records"])
    second_hashes = sorted(row["model_hash"] for row in second["outputs"]["ltr_model_artifact"]["records"])
    assert first_hashes == second_hashes
