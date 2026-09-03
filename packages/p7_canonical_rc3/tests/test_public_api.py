def test_all_stage_apis_import():
    from quant_pipeline.phase_07_strategy_tournament.foundation import run_subphase_s1, run_subphase_s2
    from quant_pipeline.phase_07_strategy_tournament.tournament import run_tournament_pipeline
    from quant_pipeline.phase_07_strategy_tournament.learning import run_s5_pipeline, run_s6_pipeline
    from quant_pipeline.phase_07_strategy_tournament.finalization import run_finalization_pipeline
    assert all(callable(x) for x in (run_subphase_s1,run_subphase_s2,run_tournament_pipeline,run_s5_pipeline,run_s6_pipeline,run_finalization_pipeline))
