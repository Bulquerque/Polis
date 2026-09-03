from datetime import datetime, timedelta
from decimal import Decimal
import json, pytest
from pydantic import ValidationError
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_common import AuditContext, content_sha256
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import LedgerEntry, ValuationRecord
from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.enums import LedgerCategory, MarkQuality

def test_extra_fields_forbidden(context):
    data=context.model_dump(); data['unknown']='x'
    with pytest.raises(ValidationError): AuditContext(**data)

def test_naive_datetime_rejected():
    with pytest.raises(ValidationError): AuditContext(run_id='r',cycle_id='c',trace_id='t',
        decision_time=datetime(2026,1,1),audit_time=datetime(2026,1,2))

def test_audit_before_decision_rejected(context):
    with pytest.raises(ValidationError): AuditContext(run_id='r',cycle_id='c',trace_id='t',
        decision_time=context.decision_time,audit_time=context.decision_time-timedelta(seconds=1))

def test_cost_positive_rejected(context):
    with pytest.raises(ValidationError): LedgerEntry(entry_id='x',category=LedgerCategory.COST,amount=Decimal('1'),event_time=context.decision_time)

def test_negative_margin_rejected(context):
    with pytest.raises(ValidationError): LedgerEntry(entry_id='x',category=LedgerCategory.MARGIN,amount=Decimal('-1'),event_time=context.decision_time)

def test_mark_semantics():
    with pytest.raises(ValidationError): ValuationRecord(instrument_id='A',quantity=Decimal('1'),mark_price=Decimal('1'),market_value=Decimal('1'),mark_quality=MarkQuality.UNAVAILABLE)
    with pytest.raises(ValidationError): ValuationRecord(instrument_id='A',quantity=Decimal('1'),mark_price=None,market_value=None,mark_quality=MarkQuality.MID)

def test_canonical_hash_order_independent():
    assert content_sha256({'b':1,'a':2})==content_sha256({'a':2,'b':1})

def test_models_frozen(context):
    with pytest.raises(ValidationError): context.run_id='other'
