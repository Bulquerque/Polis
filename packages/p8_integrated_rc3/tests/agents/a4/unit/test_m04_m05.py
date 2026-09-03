from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine import m01_timeline, m02_execution_state, m03_positions, m04_accounting, m05_valuation


def _state(value):
    q=m01_timeline.execute(value); e=m02_execution_state.execute(value,q); p=m03_positions.execute(value,q,e)
    return q,e,p


def test_accounting_balances_trade_and_fee(s8_linear_input):
    q,e,p=_state(s8_linear_input)
    result=m04_accounting.execute(s8_linear_input,q,p)
    assert result.balanced
    assert result.accounts[0].cash_available==Decimal("8989.90")
    assert sum((x.amount for x in result.cost_ledger),Decimal("0"))==Decimal("0.10")
    assert all(entry.postings for entry in result.journal_entries)


def test_valuation_nav_and_pnl(s8_linear_input):
    q,e,p=_state(s8_linear_input); a=m04_accounting.execute(s8_linear_input,q,p)
    result=m05_valuation.execute(s8_linear_input,p,a)
    assert result.nav.total_nav==Decimal("10009.90")
    assert result.positions[0].unrealized_pnl==Decimal("10")
    assert result.nav.period_pnl==Decimal("9.90")
    assert result.drawdown.drawdown_fraction==Decimal("0")
