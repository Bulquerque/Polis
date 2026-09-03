from __future__ import annotations

import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.risk_state.arrays import (
    DependenceArrays, GreekPathArrays, ScenarioPnLCube,
)
from quant_pipeline.phase_08_portfolio_control.risk_state.errors import NumericalIntegrityError


def test_pnl_cube_rejects_bad_metadata():
    with pytest.raises(NumericalIntegrityError):
        ScenarioPnLCube(
            candidate_pnl=np.zeros((2, 1, 1)),
            leg_pnl=np.zeros((2, 1, 1)),
            stress_candidate_pnl=np.zeros((1, 1, 1)),
            stress_leg_pnl=np.zeros((1, 1, 1)),
            probabilities=np.asarray([0.5, 0.5]),
            scenario_ids=("a",),
            stress_ids=("s",),
            step_labels=("t",),
            candidate_ids=("c",),
            leg_ids=("l",),
            leg_candidate_ids=("c",),
        )


def test_dependence_arrays_reject_bad_shape():
    with pytest.raises(NumericalIntegrityError):
        DependenceArrays(
            covariance=np.eye(2), correlation=np.eye(2),
            lower_tail_dependence=np.eye(2), upper_tail_dependence=np.eye(2),
            tail_asymmetry=np.eye(2), candidate_ids=("only-one",),
        )


def test_greek_arrays_reject_coverage_outside_range():
    with pytest.raises(NumericalIntegrityError):
        GreekPathArrays(
            candidate_greeks=np.zeros((1, 5)), greek_coverage=np.full((1, 5), 2.0),
            current_portfolio_greeks=np.zeros(5), mean_max_drawdown=np.zeros(1),
            tail_max_drawdown=np.zeros(1), worst_step_loss=np.zeros(1),
            candidate_ids=("c",), greek_names=("d", "g", "v", "t", "r"),
        )


def test_arrays_are_read_only(s4_request):
    from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube
    cube, _ = build_pnl_cube(
        s4_request.scenario_artifacts, s4_request.candidates,
        s4_request.factor_definitions, s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    with pytest.raises(ValueError):
        cube.candidate_pnl[0, 0, 0] = 1.0
