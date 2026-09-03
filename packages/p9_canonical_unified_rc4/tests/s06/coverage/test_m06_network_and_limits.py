from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import S6State
from quant_pipeline.phase_09.subphases.s06_structural_stress.m06_liquidity_capacity_crowding_and_fire_sale_engine import (
    evaluate_capacity,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import NetworkStressInput
from quant_pipeline.phase_09.subphases.s06_structural_stress.policies import CapacityStressPolicy


def test_stable_network_produces_amplification(capacity_request):
    network = NetworkStressInput(
        overlap_matrix=((0.1, 0.05), (0.02, 0.1)),
        initial_forced_sale=(1.0, 0.5),
    )
    result = evaluate_capacity(capacity_request.model_copy(update={"network_stress": network}))
    assert result.network_spectral_radius is not None
    assert result.network_loss_amplification > 1.0


def test_unstable_network_is_research_only(capacity_request):
    network = NetworkStressInput(
        overlap_matrix=((1.0, 0.2), (0.2, 1.0)),
        initial_forced_sale=(1.0, 1.0),
    )
    result = evaluate_capacity(capacity_request.model_copy(update={"network_stress": network}))
    assert result.status in {S6State.NETWORK_STRESS_RESEARCH_ONLY, S6State.CAPACITY_LIMITED}
    assert "P9_STRESS_NETWORK_AMPLIFICATION_UNSTABLE" in result.reason_codes


def test_margin_limit_can_bind(capacity_request):
    policy = CapacityStressPolicy(margin_limit_fraction=0.1)
    result = evaluate_capacity(capacity_request.model_copy(update={"policy": policy}))
    assert result.capacity_limit_aum is None
    assert result.status is S6State.CAPACITY_LIMITED


def test_participation_limit_and_interpolated_break_even(capacity_request):
    high_turnover = capacity_request.model_copy(
        update={"annual_turnover_ratio": 500.0, "annual_gross_return": 0.05}
    )
    result = evaluate_capacity(high_turnover)
    assert any(not point.feasible for point in result.points)
    assert result.status is S6State.CAPACITY_LIMITED


def test_exact_break_even_can_produce_fully_qualified_curve(capacity_request):
    calibration_request = capacity_request.model_copy(
        update={"annual_gross_return": 0.0, "base_aum": 20_000_000.0}
    )
    calibration = evaluate_capacity(calibration_request)
    exact_cost = calibration.points[0].annual_cost_fraction
    request = calibration_request.model_copy(update={"annual_gross_return": exact_cost})
    result = evaluate_capacity(request)
    assert result.break_even_aum == request.aum_grid[0]
    assert result.status is S6State.QUALIFIED


def test_zero_network_shock_has_zero_amplification(capacity_request):
    network = NetworkStressInput(
        overlap_matrix=((0.1, 0.0), (0.0, 0.1)),
        initial_forced_sale=(0.0, 0.0),
    )
    result = evaluate_capacity(capacity_request.model_copy(update={"network_stress": network}))
    assert result.network_loss_amplification == 0.0
