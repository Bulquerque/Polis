from __future__ import annotations

import numpy as np

from quant_pipeline.phase_08_portfolio_control.risk_state.arrays import ScenarioPnLCube
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.dependence import build_dependence
from quant_pipeline.phase_08_portfolio_control.risk_state.modules.pnl_cube import build_pnl_cube


def _cube(s4_request):
    return build_pnl_cube(
        s4_request.scenario_artifacts, s4_request.candidates,
        s4_request.factor_definitions, s4_request.step_year_fractions, s4_request.pnl_policy,
    )[0]


def test_covariance_is_psd_and_tail_matrices_bounded(s4_request):
    arrays, summary = build_dependence(_cube(s4_request), s4_request.dependence_policy)
    eigenvalues = np.linalg.eigvalsh(arrays.covariance)
    assert eigenvalues.min() >= -1e-9
    assert np.all((arrays.lower_tail_dependence >= 0) & (arrays.lower_tail_dependence <= 1))
    assert np.all((arrays.upper_tail_dependence >= 0) & (arrays.upper_tail_dependence <= 1))
    assert 0.0 <= summary.shrinkage_alpha <= 1.0


def test_candidate_permutation_only_permutes_dependence(s4_request):
    cube = _cube(s4_request)
    permuted = ScenarioPnLCube(
        candidate_pnl=cube.candidate_pnl[:, :, ::-1],
        leg_pnl=cube.leg_pnl[:, :, ::-1],
        stress_candidate_pnl=cube.stress_candidate_pnl[:, :, ::-1],
        stress_leg_pnl=cube.stress_leg_pnl[:, :, ::-1],
        probabilities=cube.probabilities,
        scenario_ids=cube.scenario_ids,
        stress_ids=cube.stress_ids,
        step_labels=cube.step_labels,
        candidate_ids=cube.candidate_ids[::-1],
        leg_ids=cube.leg_ids[::-1],
        leg_candidate_ids=cube.leg_candidate_ids[::-1],
    )
    original, _ = build_dependence(cube, s4_request.dependence_policy)
    changed, _ = build_dependence(permuted, s4_request.dependence_policy)
    np.testing.assert_allclose(original.covariance[::-1, ::-1], changed.covariance)


def test_small_effective_sample_degrades(s4_request):
    policy = s4_request.dependence_policy.model_copy(update={"minimum_effective_samples": 10_000})
    _, summary = build_dependence(_cube(s4_request), policy)
    assert summary.quality.value == "DEGRADED"
    assert "TAIL_SAMPLE_INSUFFICIENT" in summary.reason_codes
