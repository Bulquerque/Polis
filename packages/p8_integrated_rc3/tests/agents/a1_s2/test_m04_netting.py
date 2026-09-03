
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_contracts.state import PositionRecord
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.errors import NettingIntegrityError
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_netting_transform_contains_coefficients_not_final_quantities():
    specs=(CandidateSpec("a",1,instrument_id="X"),CandidateSpec("b",2,instrument_id="X"))
    bundle,context=build_input(specs)
    transform=run_s2(S2RunRequest(bundle,context)).m04.netting_transform
    assert len(transform.coefficients)==2
    assert transform.proof.contains_final_target_quantities is False
    assert "target_quantity" not in transform.model_dump_json()


def test_opposite_candidates_have_opposite_coefficients():
    from quant_pipeline.phase_08_contracts.enums import PositionSide
    specs=(CandidateSpec("a",1,instrument_id="X",side=PositionSide.LONG),CandidateSpec("b",2,instrument_id="X",side=PositionSide.SHORT))
    bundle,context=build_input(specs)
    coeff={row.candidate_id:row.signed_contracts_per_candidate_unit for row in run_s2(S2RunRequest(bundle,context)).m04.netting_transform.coefficients}
    assert coeff=={"a":Decimal("1"),"b":Decimal("-1")}


def test_current_position_is_baseline_not_attributed_to_candidates():
    pos=PositionRecord(instrument_id="X",quantity=Decimal("3"),contract_multiplier=Decimal("100"),currency="USD")
    bundle,context=build_input((CandidateSpec("a",1,instrument_id="X"),),positions=(pos,))
    baseline=run_s2(S2RunRequest(bundle,context)).m04.netting_transform.current_positions[0]
    assert baseline.current_contract_quantity==3
    assert baseline.virtual_attribution_status=="UNAVAILABLE_IN_S1_STATE"


def test_current_position_multiplier_conflict_is_fatal():
    pos=PositionRecord(instrument_id="X",quantity=Decimal("3"),contract_multiplier=Decimal("1"),currency="USD")
    bundle,context=build_input((CandidateSpec("a",1,instrument_id="X",multiplier=Decimal("100")),),positions=(pos,))
    with pytest.raises(NettingIntegrityError):
        run_s2(S2RunRequest(bundle,context))
