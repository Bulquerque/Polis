from copy import deepcopy

import pytest

from conftest import external_artifact
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import run_phase


def test_hash_tampering_is_rejected(inputs, configuration):
    inputs=deepcopy(inputs); inputs["clean_option_contract_panel"]["records"][0]["strike"]="999"
    with pytest.raises(Phase6ContractError) as error: run_phase(inputs,configuration)
    assert error.value.reason_code == "P6_MANIFEST_REFERENCE_INVALID"


def test_unknown_exercise_style_is_rejected(inputs, configuration):
    inputs=deepcopy(inputs); inputs["clean_option_contract_panel"]["records"][0]["exercise_style"]="UNKNOWN"; inputs["clean_option_contract_panel"]=external_artifact("contracts",inputs["clean_option_contract_panel"]["records"])
    with pytest.raises(Phase6ContractError): run_phase(inputs,configuration)


def test_american_options_are_fail_closed(inputs, configuration):
    inputs=deepcopy(inputs)
    for row in inputs["clean_option_contract_panel"]["records"]: row["exercise_style"]="AMERICAN"
    inputs["clean_option_contract_panel"]=external_artifact("contracts",inputs["clean_option_contract_panel"]["records"])
    result=run_phase(inputs,configuration)
    assert result["outputs"]["eligible_option_contract_panel"].record_count==0
    assert result["canonical_outputs"]["strategy_candidate_panel"].record_count<=1


def test_missing_iv_blocks_option_candidates(inputs, configuration):
    inputs=deepcopy(inputs)
    for row in inputs["clean_option_quotes_panel"]["records"]: row["implied_volatility"]=None
    inputs["clean_option_quotes_panel"]=external_artifact("quotes",inputs["clean_option_quotes_panel"]["records"])
    result=run_phase(inputs,configuration)
    assert all(len(candidate.legs)==1 and candidate.legs[0].instrument_type.value=="UNDERLYING" for candidate in result["canonical_outputs"]["strategy_candidate_panel"].records)


def test_forbidden_ranking_field_is_rejected(inputs, configuration):
    inputs=deepcopy(inputs); inputs["market_belief_state"]["records"][0]["rank_score"]=1; inputs["market_belief_state"]=external_artifact("belief",inputs["market_belief_state"]["records"])
    with pytest.raises(Phase6ContractError): run_phase(inputs,configuration)


def test_mixed_currency_candidate_is_blocked(inputs, configuration):
    from quant_pipeline.phase_06_strategy_synthesis.foundation.configuration import (
        Phase6RunConfiguration,
    )
    from quant_pipeline.phase_06_strategy_synthesis.subphase_08_feasibility_defined_risk.services import (
        initial_structural_gate,
    )

    result = run_phase(inputs, configuration)
    candidate = result["outputs"]["raw_strategy_candidate_panel"].records[0]
    altered_leg = candidate.legs[0].model_copy(update={"currency": "EUR"})
    second_leg = altered_leg.model_copy(
        update={"leg_id": "second-leg", "instrument_id": "second-instrument", "currency": "USD"}
    )
    mixed = candidate.model_copy(update={"legs": (altered_leg, second_leg)})
    policy = Phase6RunConfiguration.model_validate(configuration)
    qualification = initial_structural_gate((mixed,), policy)[0]
    assert "P6_MIXED_CURRENCY_UNSUPPORTED" in qualification.reason_codes
