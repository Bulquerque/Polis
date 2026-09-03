from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine import m01_timeline,m02_execution_state,m03_positions,m04_accounting,m05_valuation,m06_management,m07_checkpoint


def _all(value):
 q=m01_timeline.execute(value);e=m02_execution_state.execute(value,q);p=m03_positions.execute(value,q,e);a=m04_accounting.execute(value,q,p);v=m05_valuation.execute(value,p,a);m=m06_management.execute(value,e,p,a,v);return q,e,p,a,v,m


def test_management_holds_when_no_trigger(s8_linear_input):
 *_,m=_all(s8_linear_input)
 assert m.actions[0].action_type.value=="HOLD"
 assert not m.reoptimization_requests


def test_checkpoint_is_deterministic(s8_linear_input):
 q,e,p,a,v,m=_all(s8_linear_input)
 first=m07_checkpoint.execute(s8_linear_input,q,e,p,a,v,m)
 second=m07_checkpoint.execute(s8_linear_input,q,e,p,a,v,m)
 assert first.content_sha256==second.content_sha256
 assert first.checkpoint.state_content_hash==second.checkpoint.state_content_hash
