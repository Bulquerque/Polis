from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import ScenarioSet
from quant_pipeline.phase_08_portfolio_control.risk_state.errors import HashMismatchError
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube


def test_linear_and_option_valuation(s4_request):
    cube, quality = build_pnl_cube(
        s4_request.scenario_artifacts,
        s4_request.candidates,
        s4_request.factor_definitions,
        s4_request.step_year_fractions,
        s4_request.pnl_policy,
    )
    assert cube.candidate_pnl.shape[2] == 2
    assert cube.leg_pnl.shape[2] == 2
    assert cube.stress_candidate_pnl.shape[0] == 1
    scenario_file = Path(s4_request.scenario_artifacts.root_path) / s4_request.scenario_artifacts.reduced_scenarios_file
    scenarios = ScenarioSet.load_npz(scenario_file)
    b_index = scenarios.factor_ids.index("B")
    np.testing.assert_allclose(cube.candidate_pnl[:, 0, 0], scenarios.values[:, 0, b_index] * 1_000.0)
    assert quality["C-LINEAR"].value == "ANALYTIC_LINEAR"
    assert quality["C-CALL"].value == "FULL_REPRICING"
    assert np.all(np.isfinite(cube.candidate_pnl))


def test_option_loses_under_joint_stress(s4_request):
    cube, _ = build_pnl_cube(
        s4_request.scenario_artifacts,
        s4_request.candidates,
        s4_request.factor_definitions,
        s4_request.step_year_fractions,
        s4_request.pnl_policy,
    )
    assert cube.stress_candidate_pnl[0, -1, 1] < 0.0


def test_artifact_hash_mismatch_is_fatal(s4_request):
    bad = s4_request.scenario_artifacts.model_copy(
        update={"reduced_scenarios_sha256": "0" * 64}
    )
    with pytest.raises(HashMismatchError):
        build_pnl_cube(
            bad,
            s4_request.candidates,
            s4_request.factor_definitions,
            s4_request.step_year_fractions,
            s4_request.pnl_policy,
        )


def test_pnl_cube_hash_is_deterministic(s4_request):
    first, _ = build_pnl_cube(
        s4_request.scenario_artifacts, s4_request.candidates,
        s4_request.factor_definitions, s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    second, _ = build_pnl_cube(
        s4_request.scenario_artifacts, s4_request.candidates,
        s4_request.factor_definitions, s4_request.step_year_fractions, s4_request.pnl_policy,
    )
    assert first.content_sha256() == second.content_sha256()
