
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_contracts.canonical import finalize_content_hash
from quant_pipeline.phase_08_contracts.enums import PositionSide
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.errors import CandidateNormalizationError
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_long_and_short_signs_are_derived_from_side():
    specs=(CandidateSpec("long",1,instrument_id="X",side=PositionSide.LONG),CandidateSpec("short",2,instrument_id="Y",side=PositionSide.SHORT))
    bundle,context=build_input(specs)
    rows={row.candidate_id:row for row in run_s2(S2RunRequest(bundle,context)).m01.normalized_intents.candidates}
    assert rows["long"].legs[0].signed_contract_quantity_per_candidate_unit==Decimal("1")
    assert rows["short"].legs[0].signed_contract_quantity_per_candidate_unit==Decimal("-1")


def test_shape_scale_keeps_unit_quantity_not_target_quantity():
    bundle,context=build_input((CandidateSpec("cand",1,unit_quantity=Decimal("2"),entry_cost=Decimal("500"),maximum_loss=Decimal("500"),margin=Decimal("500")),))
    row=run_s2(S2RunRequest(bundle,context)).m01.normalized_intents.candidates[0]
    assert row.legs[0].contract_quantity_per_candidate_unit==2
    assert "target" not in row.model_dump_json().lower()


def test_negative_p6_unit_quantity_rejected_by_s2():
    bundle,context=build_input()
    evidence=bundle.resolved_evidence.candidates[0]
    package=evidence.p6_package
    leg=package.legs[0].model_copy(update={"unit_quantity":Decimal("-1")})
    package=package.model_copy(update={"legs":(leg,)})
    evidence=evidence.model_copy(update={"p6_package":package})
    index=bundle.resolved_evidence.model_copy(update={"candidates":(evidence,)})
    snapshot=finalize_content_hash(bundle.snapshot.model_copy(update={"resolved_evidence_hash":__import__('quant_pipeline.phase_08_contracts.canonical',fromlist=['canonical_sha256']).canonical_sha256(index)}))
    broken=finalize_content_hash(bundle.model_copy(update={"resolved_evidence":index,"snapshot":snapshot}))
    with pytest.raises(CandidateNormalizationError):
        run_s2(S2RunRequest(broken,context))


def test_model_contract_rejects_inconsistent_signed_quantity():
    from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.intent import NormalizedLeg
    from quant_pipeline.phase_08_contracts.enums import ExerciseStyle,SettlementType
    with pytest.raises(ValidationError):
        NormalizedLeg(leg_id="l",instrument_id="x",instrument_type="OPTION",side=PositionSide.LONG,
            contract_quantity_per_candidate_unit=Decimal("1"),signed_contract_quantity_per_candidate_unit=Decimal("-1"),
            contract_multiplier=Decimal("1"),exercise_style=ExerciseStyle.NONE,settlement_type=SettlementType.CASH,
            instrument_master_hash="0"*64)
