from copy import deepcopy
from datetime import timedelta

import pytest

from conftest import DECISION_TIME, external_artifact
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import run_phase


def test_future_quote_is_rejected(inputs, configuration):
    inputs=deepcopy(inputs)
    inputs["clean_option_quotes_panel"]["records"][0]["available_at"]=(DECISION_TIME+timedelta(seconds=1)).isoformat()
    inputs["clean_option_quotes_panel"]=external_artifact("quotes",inputs["clean_option_quotes_panel"]["records"])
    with pytest.raises(Phase6ContractError) as error:
        run_phase(inputs,configuration)
    assert error.value.reason_code == "P6_MARKET_CLOCK_MISMATCH"


def test_future_data_non_interference(inputs, configuration):
    base=run_phase(deepcopy(inputs),configuration)
    extended=deepcopy(inputs)
    future=deepcopy(extended["clean_option_quotes_panel"]["records"][0])
    future["contract_id"]="UNUSED-FUTURE"
    future["available_at"]=(DECISION_TIME+timedelta(days=1)).isoformat()
    # Future records are rejected rather than silently changing the past.
    extended["clean_option_quotes_panel"]["records"].append(future)
    extended["clean_option_quotes_panel"]=external_artifact("quotes",extended["clean_option_quotes_panel"]["records"])
    with pytest.raises(Phase6ContractError):
        run_phase(extended,configuration)
    assert base["canonical_outputs"]["strategy_candidate_panel"].record_count > 0


def test_crossed_quote_is_removed_not_repaired(inputs, configuration):
    inputs=deepcopy(inputs)
    inputs["clean_option_quotes_panel"]["records"][0]["bid"]="30"
    inputs["clean_option_quotes_panel"]["records"][0]["ask"]="20"
    inputs["clean_option_quotes_panel"]=external_artifact("quotes",inputs["clean_option_quotes_panel"]["records"])
    result=run_phase(inputs,configuration)
    report=result["outputs"]["static_arbitrage_report"]
    assert any(row.violation_type=="BID_ABOVE_ASK" for row in report.records)
    assert result["outputs"]["arbitrage_validated_option_quote_panel"].metadata["repair_applied"] is False


def test_phantom_contract_never_generates_candidate(inputs, configuration):
    result=run_phase(inputs,configuration)
    known={row["contract_id"] for row in inputs["clean_option_contract_panel"]["records"]}
    for candidate in result["outputs"]["raw_strategy_candidate_panel"].records:
        assert all(leg.instrument_id in known or leg.instrument_type.value=="UNDERLYING" for leg in candidate.legs)
