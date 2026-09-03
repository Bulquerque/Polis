import hashlib
import pytest

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.compat.rc4_1 import adapt_rc4_1_belief
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import ParametricPayload
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.errors import CapabilityUnavailableError


def legacy_record(now):
    return {
        "belief_state_id":"legacy", "target_id":"A", "factor_ids":["A"],
        "forecast_horizon_hours":24, "available_at":now.isoformat(), "decision_time":now.isoformat(),
        "expected_return":0.1, "volatility":0.2,
    }


def test_adapter_refuses_synthetic_distribution(now):
    with pytest.raises(CapabilityUnavailableError):
        adapt_rc4_1_belief(legacy_record(now), None, hashlib.sha256(b"x").hexdigest())


def test_adapter_accepts_resolved_payload(now):
    payload = ParametricPayload(family="NORMAL", mean=(0.1,), covariance=((0.04,),))
    belief = adapt_rc4_1_belief(legacy_record(now), payload, hashlib.sha256(b"x").hexdigest())
    assert belief.payload == payload
