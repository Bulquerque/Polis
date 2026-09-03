from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality, CausalStrength
from quant_pipeline.phase_09.subphases.s08_attribution.m08_reconciliation import ReconciliationPolicy, reconcile_attribution
from quant_pipeline.phase_09.subphases.s08_attribution.runner import S8Pipeline


def _results(valid_request):
    bundle=S8Pipeline().run(valid_request)
    p=bundle.payload
    return p.forecast_attribution,p.payoff_attribution,p.ranking_attribution,p.portfolio_attribution,p.execution_attribution,p.option_attribution,p.counterfactual_report


def test_exact_reconciliation(valid_request):
    forecast,payoff,ranking,portfolio,execution,options,counterfactual=_results(valid_request)
    result=reconcile_attribution(6.0,forecast,payoff,ranking,portfolio,execution,options,counterfactual,"HEALTHY",ReconciliationPolicy())
    assert result.reconciliation.reconciled
    assert result.reconciliation.residual_pnl == 0.0
    assert result.quality is AttributionQuality.QUALIFIED


def test_material_residual_invalidates(valid_request):
    forecast,payoff,ranking,portfolio,execution,options,counterfactual=_results(valid_request)
    result=reconcile_attribution(7.0,forecast,payoff,ranking,portfolio,execution,options,counterfactual,"HEALTHY",ReconciliationPolicy())
    assert not result.reconciliation.reconciled
    assert result.quality is AttributionQuality.INVALID


def test_option_and_counterfactual_are_not_added_twice(valid_request):
    forecast,payoff,ranking,portfolio,execution,options,counterfactual=_results(valid_request)
    result=reconcile_attribution(6.0,forecast,payoff,ranking,portfolio,execution,options,counterfactual,"HEALTHY",ReconciliationPolicy())
    assert sum(item.pnl_effect for item in result.stage_amounts) == 6.0
    assert result.option_nested_explanation.full_repricing_pnl == 1.0
    assert result.counterfactual_diagnostic.doubly_robust_value == 1.0


def test_live_degradation_is_plausible_not_supported(valid_request):
    forecast,payoff,ranking,portfolio,execution,options,counterfactual=_results(valid_request)
    result=reconcile_attribution(6.0,forecast,payoff,ranking,portfolio,execution,options,counterfactual,"ROLLBACK_RECOMMENDED",ReconciliationPolicy())
    node=next(item for item in result.root_cause_nodes if item.cause_id=="CAUSE_LIVE_DEGRADATION")
    assert node.causal_strength is CausalStrength.PLAUSIBLE
