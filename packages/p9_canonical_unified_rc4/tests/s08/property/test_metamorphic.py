from quant_pipeline.phase_09.subphases.s08_attribution.m01_forecast_attribution import attribute_forecast_components
from quant_pipeline.phase_09.subphases.s08_attribution.m02_payoff_attribution import evaluate_payoff_fidelity
from quant_pipeline.phase_09.subphases.s08_attribution.m03_ranking_attribution import evaluate_ranking
from quant_pipeline.phase_09.subphases.s08_attribution.m05_execution_attribution import attribute_execution_and_lifecycle


def test_forecast_attribution_is_permutation_invariant(valid_request):
    first=attribute_forecast_components(valid_request.forecast_observations, valid_request.forecast_policy)
    second=attribute_forecast_components(tuple(reversed(valid_request.forecast_observations)), valid_request.forecast_policy)
    assert first == second


def test_payoff_attribution_is_permutation_invariant(valid_request):
    first=evaluate_payoff_fidelity(valid_request.payoff_scenario_points, valid_request.candidate_outcomes, valid_request.payoff_policy)
    second=evaluate_payoff_fidelity(tuple(reversed(valid_request.payoff_scenario_points)), tuple(reversed(valid_request.candidate_outcomes)), valid_request.payoff_policy)
    assert first == second


def test_ranking_group_order_does_not_change_aggregate(valid_request):
    group=valid_request.ranking_groups[0]
    reversed_group=group.model_copy(update={"candidates":tuple(reversed(group.candidates))})
    first=evaluate_ranking((group,), valid_request.ranking_policy)
    second=evaluate_ranking((reversed_group,), valid_request.ranking_policy)
    assert first.mean_pairwise_accuracy == second.mean_pairwise_accuracy
    assert first.total_ranking_regret == second.total_ranking_regret


def test_higher_fees_cannot_improve_execution_effect(valid_request):
    base=attribute_execution_and_lifecycle(valid_request.execution_records, valid_request.lifecycle_events, valid_request.execution_policy)
    costly=tuple(item.model_copy(update={"fees":item.fees+1.0}) for item in valid_request.execution_records)
    stressed=attribute_execution_and_lifecycle(costly, valid_request.lifecycle_events, valid_request.execution_policy)
    assert stressed.aggregate_pnl_effect < base.aggregate_pnl_effect
