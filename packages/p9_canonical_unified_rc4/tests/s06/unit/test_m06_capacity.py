from quant_pipeline.phase_09.subphases.s06_structural_stress.m06_liquidity_capacity_crowding_and_fire_sale_engine import (
    evaluate_capacity,
)


def test_capacity_costs_increase_with_aum(capacity_request):
    result = evaluate_capacity(capacity_request)
    costs = [point.annual_cost_fraction for point in result.points]
    assert costs == sorted(costs)
    assert result.points[-1].net_return < result.points[0].net_return


def test_capacity_marks_extrapolated_points(capacity_request):
    result = evaluate_capacity(capacity_request)
    assert result.points[0].evidence_class.value == "OBSERVED_HISTORICAL"
    assert result.points[-1].evidence_class.value == "STRESS_EXTRAPOLATED"
