from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s1


def test_full_s1_runner(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    result = run_subphase_s1(
        phase6_manifest=manifest,
        phase6_artifacts=artifacts,
        module_config=module_config,
    )
    assert result["outputs"]["temporally_safe_candidate_bundle"]["record_count"] == 1
    assert result["outputs"]["ranking_feedback_context"]["record_count"] == 0
