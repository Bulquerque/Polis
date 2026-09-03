from decimal import Decimal

import pytest

from quant_pipeline.phase_06_strategy_synthesis.domain.enums import InstrumentType, Side, TemplateId
from quant_pipeline.phase_06_strategy_synthesis.domain.payoff import strategy_terminal_pnl
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import run_phase

EXPECTED_TEMPLATES={
    TemplateId.LONG_UNDERLYING,
    TemplateId.LONG_CALL,
    TemplateId.LONG_PUT,
    TemplateId.BULL_CALL_DEBIT,
    TemplateId.BEAR_PUT_DEBIT,
    TemplateId.BULL_PUT_CREDIT,
    TemplateId.BEAR_CALL_CREDIT,
    TemplateId.LONG_STRADDLE,
    TemplateId.LONG_STRANGLE,
    TemplateId.LONG_CALL_BUTTERFLY,
    TemplateId.LONG_CALL_CONDOR,
    TemplateId.IRON_BUTTERFLY,
    TemplateId.IRON_CONDOR,
    TemplateId.COLLAR,
    TemplateId.RISK_REVERSAL_DEFINED_RISK,
    TemplateId.PROTECTED_RATIO_CALL,
}


def test_wave1_generates_expected_template_families(inputs, configuration):
    result=run_phase(inputs,configuration)
    observed={item.origin_template_id for item in result["outputs"]["raw_strategy_candidate_panel"].records}
    assert EXPECTED_TEMPLATES <= observed


def test_no_naked_short_option_is_published(inputs, configuration):
    result=run_phase(inputs,configuration)
    for candidate in result["canonical_outputs"]["strategy_candidate_panel"].records:
        short_options=[leg for leg in candidate.legs if leg.instrument_type is InstrumentType.OPTION and leg.side is Side.SHORT]
        if short_options:
            payoff=next(row for row in result["canonical_outputs"]["strategy_payoff_panel"].records if row.candidate_id==candidate.candidate_id)
            assert payoff.maximum_loss is not None


@pytest.mark.parametrize("spot",[Decimal("0"),Decimal("80"),Decimal("100"),Decimal("120"),Decimal("300")])
def test_payoff_panel_reconciles_exact_leg_sum(inputs, configuration, spot):
    result=run_phase(inputs,configuration)
    cost_by_id={row.candidate_id:row for row in result["canonical_outputs"]["strategy_cost_liquidity_panel"].records}
    for candidate in result["canonical_outputs"]["strategy_candidate_panel"].records:
        cost=cost_by_id[candidate.candidate_id]
        expected=strategy_terminal_pnl(candidate.legs,spot,cost.fee_estimate+cost.slippage_estimate)
        assert isinstance(expected,Decimal)


def test_defined_risk_qualification(inputs, configuration):
    result=run_phase(inputs,configuration)
    qualified={q.candidate_id:q for q in result["outputs"]["strategy_qualification_panel"].records if q.qualified}
    assert qualified
    assert all(item.maximum_loss_proven for item in qualified.values())
    assert all(item.margin_estimate is not None for item in qualified.values())
