from __future__ import annotations

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_portfolio_control.risk_state.contracts import (
    CandidateEconomicPackage, FactorDefinition, ShockKind, S4Request,
)


def test_public_contract_rejects_unknown_fields(linear_candidate):
    payload = linear_candidate.model_dump(mode="json")
    payload["portfolio_weight"] = 0.5
    with pytest.raises(ValidationError):
        CandidateEconomicPackage.model_validate(payload)


def test_factor_definition_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        FactorDefinition.model_validate({
            "factor_id": "A", "shock_kind": ShockKind.LOG_RETURN,
            "unit": "LOG_RETURN", "extra": 1,
        })


def test_multi_currency_requires_explicit_adapter(s4_request, option_candidate):
    eur_leg = option_candidate.legs[0].model_copy(update={"currency": "EUR"})
    eur = option_candidate.model_copy(update={
        "currency": "EUR", "candidate_id": "EUR-CALL", "legs": (eur_leg,),
    })
    payload = s4_request.model_dump(mode="python")
    payload["candidates"] = (s4_request.candidates[0], eur)
    with pytest.raises(ValidationError):
        S4Request.model_validate(payload)
