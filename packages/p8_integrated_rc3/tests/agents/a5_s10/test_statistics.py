from decimal import Decimal
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_qualification import StatisticalEvidence
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.statistical_readiness import (
    build_diagnostics, deflated_sharpe_ratio, probability_backtest_overfitting)

def test_diagnostics_present(statistical):
    d=build_diagnostics(statistical)
    assert d.observation_count==40
    assert d.sharpe_ratio is not None and d.deflated_sharpe_ratio is not None
    assert d.probability_backtest_overfitting is not None

def test_short_returns_have_no_dsr(statistical):
    item=statistical.model_copy(update={'returns':(Decimal('1'),Decimal('1'))})
    assert deflated_sharpe_ratio(item) is None

def test_zero_variance_dsr_none(statistical):
    item=statistical.model_copy(update={'returns':tuple(Decimal('1') for _ in range(10))})
    assert deflated_sharpe_ratio(item) is None

def test_invalid_pbo_shapes(statistical):
    assert probability_backtest_overfitting(statistical.model_copy(update={'strategy_returns':()})) is None
    odd=((Decimal('1'),Decimal('2')),)*5
    assert probability_backtest_overfitting(statistical.model_copy(update={'strategy_returns':odd})) is None
    ragged=((Decimal('1'),Decimal('2')),(Decimal('1'),))*4
    assert probability_backtest_overfitting(statistical.model_copy(update={'strategy_returns':ragged})) is None

def test_single_trial_supported(statistical):
    item=statistical.model_copy(update={'trial_sharpes':(Decimal('0.2'),)})
    assert deflated_sharpe_ratio(item) is not None
