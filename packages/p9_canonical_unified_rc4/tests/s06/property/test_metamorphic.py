from quant_pipeline.phase_09.subphases.s06_structural_stress.m06_liquidity_capacity_crowding_and_fire_sale_engine import (
    evaluate_capacity,
)


def test_higher_impact_coefficient_never_improves_net_return(capacity_request):
    baseline = evaluate_capacity(capacity_request)
    changed_legs = tuple(
        leg.model_copy(update={"impact_coefficient_bps": leg.impact_coefficient_bps * 2.0})
        for leg in capacity_request.legs
    )
    stressed = evaluate_capacity(capacity_request.model_copy(update={"legs": changed_legs}))
    assert all(
        right.net_return <= left.net_return + 1e-12
        for left, right in zip(baseline.points, stressed.points)
    )
