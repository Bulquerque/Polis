
from decimal import Decimal
import json
from pathlib import Path

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_output_determinism():
    bundle,context=build_input((CandidateSpec("a",1),CandidateSpec("b",2,instrument_id="Y")))
    first=run_s2(S2RunRequest(bundle,context)).bundle
    second=run_s2(S2RunRequest(bundle,context)).bundle
    assert first==second
    assert canonical_sha256(first,exclude_keys=frozenset({"content_sha256"}))==first.content_sha256


def test_scale_equivalence_property_for_multiple_positive_scales():
    for factor in (Decimal("2"),Decimal("3"),Decimal("10")):
        specs=(CandidateSpec("a",1,instrument_id="X",canonical_candidate_id="canon",p5_variant="same"),
               CandidateSpec("b",2,instrument_id="X",unit_quantity=factor,entry_cost=Decimal("250")*factor,maximum_loss=Decimal("250")*factor,margin=Decimal("250")*factor,canonical_candidate_id="canon",p5_variant="same"))
        bundle,context=build_input(specs)
        group=run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups[0]
        assert group.members[1].scale_factor_from_representative==factor


def test_no_output_contains_forbidden_financial_authority_fields():
    bundle,context=build_input()
    payload=run_s2(S2RunRequest(bundle,context)).bundle.model_dump(mode="python")
    forbidden={"expected_return","scenario_probability","portfolio_weight","final_position_size","execution_price"}
    def keys(value):
        if isinstance(value,dict):
            for key,item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value,(list,tuple)):
            for item in value:
                yield from keys(item)
    assert forbidden.isdisjoint(set(keys(payload)))


def test_receipts_cover_all_modules_and_output():
    bundle,context=build_input()
    result=run_s2(S2RunRequest(bundle,context))
    ids=[result.m01.receipt.module_id,result.m02.receipt.module_id,result.m03.receipt.module_id,
         result.m04.receipt.module_id,result.m05.receipt.module_id,result.m06.receipt.module_id,result.output.receipt.module_id]
    assert ids==["P8.S2.M01","P8.S2.M02","P8.S2.M03","P8.S2.M04","P8.S2.M05","P8.S2.M06","P8.S2.OUTPUT"]
