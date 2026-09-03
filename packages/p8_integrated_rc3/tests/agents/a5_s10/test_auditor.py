from decimal import Decimal
import pytest
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import AuditOverallStatus, MarkQuality
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.independent_auditor import run_independent_audit

def statuses(report): return {c.check_id:c.status.value for c in report.checks}

def test_valid_bundle_passes(bundle):
    report=run_independent_audit(bundle)
    assert report.overall_status==AuditOverallStatus.PASS
    assert report.failure_count==0 and report.warning_count==0
    assert report.independent_implementation is True
    assert report.production_promotion_allowed is False

@pytest.mark.parametrize('field,update,check',[
 ('expected_candidate_ids',('c1','c2','c3'),'candidate_conservation'),
 ('final_positions',(), 'position_reconciliation'),
 ('virtual_allocations',(), 'dual_book_reconciliation'),
])
def test_conservation_failures(bundle,field,update,check):
    report=run_independent_audit(bundle.model_copy(update={field:update}))
    assert statuses(report)[check]=='FAIL'

@pytest.mark.parametrize('name,changes,expected_check',[
 ('order',{'total_quantity':Decimal('3')},'order_conservation:o1'),
 ('fill',{'quantity':Decimal('1')},'fill_sum:o1'),
])
def test_order_fill_failures(bundle,name,changes,expected_check):
    key='orders' if name=='order' else 'fills'; item=getattr(bundle,key)[0].model_copy(update=changes)
    report=run_independent_audit(bundle.model_copy(update={key:(item,)}))
    assert statuses(report)[expected_check]=='FAIL'

def test_cash_margin_and_collateral_failures(bundle):
    account=bundle.account_snapshot.model_copy(update={'final_cash':Decimal('980'),'margin_used':Decimal('6'),'collateral_value':Decimal('1')})
    report=run_independent_audit(bundle.model_copy(update={'account_snapshot':account}))
    s=statuses(report)
    assert s['cash_reconciliation']==s['margin_reconciliation']==s['collateral_reconciliation']=='FAIL'

def test_valuation_nav_and_pnl_failures(bundle):
    val=bundle.valuations[0].model_copy(update={'market_value':Decimal('20')})
    pnl=bundle.pnl_snapshot.model_copy(update={'total_pnl':Decimal('4')})
    report=run_independent_audit(bundle.model_copy(update={'valuations':(val,),'pnl_snapshot':pnl}))
    s=statuses(report)
    assert s['valuation:A']=='FAIL'; assert s['pnl_components']=='FAIL'; assert s['nav_to_pnl']=='FAIL'

def test_unavailable_mark_is_incomplete(bundle):
    val=bundle.valuations[0].model_copy(update={'mark_price':None,'market_value':None,'mark_quality':MarkQuality.UNAVAILABLE})
    report=run_independent_audit(bundle.model_copy(update={'valuations':(val,)}))
    assert report.overall_status==AuditOverallStatus.INCOMPLETE
    assert report.warning_count==2

def test_replay_hash_and_sequence_failures(bundle):
    cp=bundle.replay_checkpoint.model_copy(update={'expected_state_sha256':'0'*64})
    reversed_events=tuple(reversed(bundle.replay_events))
    report=run_independent_audit(bundle.model_copy(update={'replay_checkpoint':cp,'replay_events':reversed_events}))
    s=statuses(report); assert s['event_sequence']=='FAIL'; assert s['replay_hash']=='FAIL'

def test_duplicate_order_and_fill_ids_detected(bundle):
    orders=(bundle.orders[0],bundle.orders[0]); fills=(bundle.fills[0],bundle.fills[0])
    report=run_independent_audit(bundle.model_copy(update={'orders':orders,'fills':fills}))
    s=statuses(report); assert s['order_id_uniqueness']=='FAIL'; assert s['fill_id_uniqueness']=='FAIL'

def test_fill_order_identity_detected(bundle):
    fill=bundle.fills[0].model_copy(update={'instrument_id':'B'})
    report=run_independent_audit(bundle.model_copy(update={'fills':(fill,)}))
    assert statuses(report)['fill_order_identity']=='FAIL'

def test_valuation_quantity_and_liability_detected(bundle):
    val=bundle.valuations[0].model_copy(update={'quantity':Decimal('3'),'market_value':Decimal('36')})
    account=bundle.account_snapshot.model_copy(update={'liabilities':Decimal('1')})
    report=run_independent_audit(bundle.model_copy(update={'valuations':(val,), 'account_snapshot':account}))
    s=statuses(report); assert s['valuation_position_reconciliation']=='FAIL'; assert s['liability_reconciliation']=='FAIL'

def test_multicurrency_accounts_reconcile_in_functional_currency(bundle):
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import LedgerCategory
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import (
        CurrencyAccountSnapshot,
        LedgerEntry,
    )

    rows = (
        CurrencyAccountSnapshot(
            currency="USD", functional_fx_rate=Decimal("1"),
            initial_cash=Decimal("1000"), final_cash=Decimal("979"),
            margin_used=Decimal("5"), collateral_value=Decimal("0"), liabilities=Decimal("0"),
        ),
        CurrencyAccountSnapshot(
            currency="EUR", functional_fx_rate=Decimal("1.2"),
            initial_cash=Decimal("100"), final_cash=Decimal("110"),
            margin_used=Decimal("0"), collateral_value=Decimal("0"), liabilities=Decimal("0"),
        ),
    )
    account = bundle.account_snapshot.model_copy(update={
        "functional_currency": "USD",
        "initial_cash": Decimal("1120"),
        "final_cash": Decimal("1111"),
        "margin_used": Decimal("5"),
        "initial_nav": Decimal("1132"),
        "currency_accounts": rows,
    })
    ledger = (
        LedgerEntry(entry_id="usd-premium", category=LedgerCategory.PREMIUM, currency="USD", amount=Decimal("-20"), event_time=bundle.context.decision_time),
        LedgerEntry(entry_id="usd-cost", category=LedgerCategory.COST, currency="USD", amount=Decimal("-1"), event_time=bundle.context.decision_time),
        LedgerEntry(entry_id="usd-margin", category=LedgerCategory.MARGIN, currency="USD", amount=Decimal("5"), event_time=bundle.context.decision_time),
        LedgerEntry(entry_id="eur-flow", category=LedgerCategory.CASH_FLOW, currency="EUR", amount=Decimal("10"), event_time=bundle.context.decision_time),
    )
    report = run_independent_audit(bundle.model_copy(update={
        "account_snapshot": account,
        "ledger_entries": ledger,
    }))
    assert report.overall_status == AuditOverallStatus.PASS


def test_multicurrency_aggregate_tampering_is_detected(bundle):
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import CurrencyAccountSnapshot

    rows = (
        CurrencyAccountSnapshot(
            currency="USD", functional_fx_rate=Decimal("1"),
            initial_cash=Decimal("1000"), final_cash=Decimal("979"),
            margin_used=Decimal("5"), collateral_value=Decimal("0"), liabilities=Decimal("0"),
        ),
    )
    account = bundle.account_snapshot.model_copy(update={
        "final_cash": Decimal("980"),
        "currency_accounts": rows,
    })
    report = run_independent_audit(bundle.model_copy(update={"account_snapshot": account}))
    assert statuses(report)["aggregate_final_cash"] == "FAIL"


def test_unavailable_pnl_remains_unavailable(bundle):
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import PnLQuality
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import PnLSnapshot

    unavailable = PnLSnapshot(
        quality=PnLQuality.UNAVAILABLE,
        realized_pnl=None,
        unrealized_pnl=None,
        costs=None,
        total_pnl=None,
    )
    report = run_independent_audit(bundle.model_copy(update={"pnl_snapshot": unavailable}))
    assert report.overall_status == AuditOverallStatus.INCOMPLETE
    assert statuses(report)["pnl_components"] == "WARNING"
    assert statuses(report)["nav_to_pnl"] == "WARNING"
