from __future__ import annotations

import copy

import pytest

from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import digest
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M01_ranking_target_policy_registry_builder import run_module as m01
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M02_counterfactual_training_dataset_builder import run_module as m02
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M03_query_group_temporal_split_planner import run_module as m03
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M04_ltr_training_orchestrator import run_module as m04
from quant_pipeline.phase_07_strategy_tournament.learning.modules.P7_S5_M05_ltr_model_qualification_gate import run_module as m05
from quant_pipeline.phase_07_strategy_tournament.learning.runner_s5 import run_s5_pipeline


def _m04_outputs(input_bundle, config):
    policies = m01(input_bundle, config)["outputs"]["ranking_target_policy_registry"]
    dataset = m02({
        "historical_tournament_snapshots": input_bundle["historical_tournament_snapshots"],
        "historical_candidate_counterfactual_outcome_panel": input_bundle["historical_candidate_counterfactual_outcome_panel"],
        "ranking_target_policy_registry": policies,
    }, config)["outputs"]["ltr_training_dataset_manifest"]
    folds = m03({"ltr_training_dataset_manifest": dataset, "trading_calendar_reference": input_bundle["trading_calendar_reference"]}, config)["outputs"]["ltr_temporal_fold_plan"]
    return m04({"ltr_training_dataset_manifest": dataset, "ltr_temporal_fold_plan": folds, "model_family_registry": input_bundle["model_family_registry"]}, config)["outputs"]


def test_unavailable_calibrator_is_not_runtime_eligible(input_bundle, config):
    outputs = _m04_outputs(input_bundle, config)
    models = copy.deepcopy(outputs["ltr_model_artifact"])
    models["records"][0]["calibrator"]["status"] = "UNAVAILABLE"
    models["records"][0]["model_hash"] = digest({k: v for k, v in models["records"][0].items() if k != "model_hash"})
    models["content_sha256"] = digest(models["records"])
    baseline = copy.deepcopy(outputs["ltr_oof_score_panel"])
    baseline["artifact_name"] = "interpretable_baseline_history"
    baseline["content_sha256"] = digest(baseline["records"])
    result = m05({**outputs, "ltr_model_artifact": models, "interpretable_baseline_history": baseline}, config)
    row = next(r for r in result["outputs"]["ltr_model_qualification_registry"]["records"] if r["model_family_id"] == models["records"][0]["model_family_id"])
    assert row["runtime_eligible"] is False
    assert row["qualification_status"] == "INSUFFICIENT_EVIDENCE"


def test_unknown_model_family_and_test_seal_fail(input_bundle, config):
    bad = copy.deepcopy(input_bundle)
    bad["model_family_registry"]["records"][0]["algorithm"] = "UNKNOWN"
    bad["model_family_registry"]["content_sha256"] = digest(bad["model_family_registry"]["records"])
    with pytest.raises(P7S5Error, match="P7_LTR_MODEL_FAMILY_INVALID"):
        run_s5_pipeline(bad, copy.deepcopy(config))
    outputs = _m04_outputs(input_bundle, config)
    assert outputs["ltr_model_artifact"]["records"]


def test_baseline_reconciliation_detects_difference(input_bundle, config):
    outputs = _m04_outputs(input_bundle, config)
    baseline = copy.deepcopy(outputs["ltr_oof_score_panel"])
    baseline["artifact_name"] = "interpretable_baseline_history"
    baseline["records"][0]["interpretable_score"] += 1.0
    baseline["content_sha256"] = digest(baseline["records"])
    with pytest.raises(ValueError, match="does not reconcile"):
        m05({**outputs, "interpretable_baseline_history": baseline}, config)


def test_qualification_report_contains_slice_and_calibration_gates(input_bundle, config):
    result = run_s5_pipeline(input_bundle, config)
    reports = result['outputs']['ltr_model_qualification_report']['records']
    assert reports
    assert all('slice_gate_summary' in row for row in reports)
    assert all('mean_absolute_error' in row['calibration_summary'] for row in reports)
    assert all('slice_quality' in row['gate_results'] and 'calibration_quality' in row['gate_results'] for row in reports)
