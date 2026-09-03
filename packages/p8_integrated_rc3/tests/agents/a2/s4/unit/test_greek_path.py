from __future__ import annotations

import pytest

from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import CandidatePosition, PhysicalPosition
from quant_pipeline.phase_08_portfolio_control.risk_state.errors import DualBookReconciliationError
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.greek_path import build_greek_path_state
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube


def _cube(request):
    return build_pnl_cube(
        request.scenario_artifacts, request.candidates, request.factor_definitions,
        request.step_year_fractions, request.pnl_policy,
    )[0]


def test_greeks_are_aggregated_and_single_step_path_is_explicit(s4_request):
    arrays, summary = build_greek_path_state(
        _cube(s4_request), s4_request.candidates, (), (),
        s4_request.greek_policy, True,
    )
    assert arrays.candidate_greeks.shape == (2, 5)
    assert summary.greek_coverage_by_candidate["C-LINEAR"] == 1.0
    assert summary.path_capability_by_candidate["C-CALL"].value == "UNAVAILABLE"
    assert "PATH_EXPOSURE_UNAVAILABLE" in summary.reason_codes


def test_virtual_physical_mismatch_is_fatal(s4_request):
    virtual = (CandidatePosition(candidate_id="C-LINEAR", units=2.0),)
    physical = (PhysicalPosition(instrument_id="INST-LINEAR", quantity=1.0),)
    with pytest.raises(DualBookReconciliationError):
        build_greek_path_state(
            _cube(s4_request), s4_request.candidates, virtual, physical,
            s4_request.greek_policy, True,
        )


def test_path_metrics_available(path_s3_artifacts, s4_request):
    result, artifacts = path_s3_artifacts
    request = s4_request.model_copy(update={
        "s3_result": result,
        "scenario_artifacts": artifacts,
        "step_year_fractions": (1/252, 2/252, 3/252),
    })
    arrays, summary = build_greek_path_state(
        _cube(request), request.candidates, (), (), request.greek_policy, True,
    )
    assert all(value.value == "FULLY_QUALIFIED" for value in summary.path_capability_by_candidate.values())
    assert arrays.mean_max_drawdown.max() >= 0.0
    assert arrays.tail_max_drawdown.max() >= arrays.mean_max_drawdown.min()
