from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.tournament.domain.enums import FactorMode
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S3_M01_candidate_metric_semantics_compiler import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S3_M02_option_factor_exposure_adjuster import run_module as run_m02

from tests.tournament.tests.s3.factories import DECISION_TIME, execution_config, make_bundle


def _run_factor_module(bundle):
    m01 = run_m01(bundle, execution_config())
    inputs = {
        "comparable_candidate_metric_panel": m01["outputs"]["comparable_candidate_metric_panel"],
        "eligible_strategy_candidate_panel": bundle["eligible_strategy_candidate_panel"],
        "ranking_policy_context": bundle["ranking_policy_context"],
    }
    if "option_factor_model_artifact" in bundle:
        inputs["option_factor_model_artifact"] = bundle["option_factor_model_artifact"]
    return run_m02(inputs, execution_config())


def test_bypass_preserves_target_and_marks_status():
    result = _run_factor_module(make_bundle())
    row = next(
        row for row in result["outputs"]["factor_adjusted_metric_panel"]["records"]
        if row["candidate_id"] == "A" and row["metric_id"] == "expected_net_payoff"
    )
    assert row["adjustment_status"] == "BYPASS"
    assert row["adjusted_raw_value"] == 12.0
    assert result["outputs"]["factor_exposure_panel"]["record_count"] == 0


def test_static_premia_adjustment_conserves_contributions():
    bundle = make_bundle(
        factor_mode=FactorMode.STATIC_PREMIA,
        static_coefficients={"delta": 2.0, "vega": 1.0},
    )
    result = _run_factor_module(bundle)
    row = next(
        row for row in result["outputs"]["factor_adjusted_metric_panel"]["records"]
        if row["candidate_id"] == "A" and row["metric_id"] == "expected_net_payoff"
    )
    assert row["adjustment_status"] == "ADJUSTED"
    assert row["total_factor_contribution"] == pytest.approx(0.4)
    assert row["adjusted_raw_value"] == pytest.approx(11.6)
    audit = result["outputs"]["factor_adjustment_audit_report"]["records"][0]
    assert audit["conservation_max_abs_error"] <= 1e-12


def test_qualified_residual_model_is_used_without_runtime_fit():
    bundle = make_bundle(factor_mode=FactorMode.QUALIFIED_RESIDUAL, include_factor_model=True)
    result = _run_factor_module(bundle)
    audit = result["outputs"]["factor_adjustment_audit_report"]["records"][0]
    assert audit["model_id"] == "factor-model-v1"
    assert audit["adjusted_candidate_count"] == 3


def test_future_factor_model_cutoff_fails_closed():
    bundle = make_bundle(
        factor_mode=FactorMode.QUALIFIED_RESIDUAL,
        include_factor_model=True,
        factor_training_cutoff=DECISION_TIME + timedelta(seconds=1),
    )
    with pytest.raises(TemporalViolation) as exc_info:
        _run_factor_module(bundle)
    assert exc_info.value.code == "P7_S3_FACTOR_MODEL_FUTURE_CUTOFF"
