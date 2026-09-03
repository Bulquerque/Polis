from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.calculations import reverse_dcf, scenario_dcf
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.models import DcfAssumptions, ReverseDcfAssumptions, ExtensionLineage, ReadinessStatus
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.readiness import build_readiness_panel


def lineage():
    return ExtensionLineage(lineage_id="lineage", producer_module_id="P3.S38.M01")


def test_readiness_blocks_missing_views_but_keeps_scenario_valuation():
    panel=build_readiness_panel(view_manifest={"views":[{"view_id":"company_profile"}]}, lineage=lineage())
    statuses={(r.operation_id,r.mode_id.value):r.status for r in panel.records}
    assert statuses[("get_profile","QUICK_CHECK")] is ReadinessStatus.AVAILABLE
    assert statuses[("get_financial_statements","QUICK_CHECK")] is ReadinessStatus.BLOCKED_UPSTREAM
    assert statuses[("calculate_valuation","QUICK_CHECK")] is ReadinessStatus.AVAILABLE


def test_scenario_dcf_and_reverse_dcf_are_consistent():
    assumptions=DcfAssumptions(base_free_cash_flow=100.0,growth_rates=(0.05,)*5,discount_rate=0.10,terminal_growth_rate=0.02,net_debt=20.0,shares_outstanding=10.0)
    result=scenario_dcf(assumptions)
    assert result["scenario_value_per_share"] > 0
    reverse=reverse_dcf(ReverseDcfAssumptions(market_price=result["scenario_value_per_share"],base_free_cash_flow=100.0,discount_rate=0.10,terminal_growth_rate=0.02,forecast_years=5,net_debt=20.0,shares_outstanding=10.0,lower_growth=-0.1,upper_growth=0.2))
    assert abs(reverse["implied_annual_growth"]-0.05) < 1e-5
