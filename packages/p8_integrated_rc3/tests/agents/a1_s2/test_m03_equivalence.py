
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import EquivalenceType
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_exact_physical_equivalence_detected_but_not_redundant_for_different_canonical_ids():
    specs=(CandidateSpec("a",1,instrument_id="X",p5_variant="same"),CandidateSpec("b",2,instrument_id="X",p5_variant="same"))
    bundle,context=build_input(specs)
    group=run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups[0]
    assert group.equivalence_type is EquivalenceType.EXACT_PHYSICAL
    assert not group.hard_redundant_eligible
    assert "DIFFERENT_CANONICAL_CANDIDATE_NOT_REDUNDANT" in group.reason_codes


def test_same_canonical_and_p5_can_be_hard_redundant():
    specs=(CandidateSpec("a",1,instrument_id="X",p5_variant="same",canonical_candidate_id="canon"),CandidateSpec("b",2,instrument_id="X",p5_variant="same",canonical_candidate_id="canon"))
    bundle,context=build_input(specs)
    group=run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups[0]
    assert group.hard_redundant_eligible


def test_scale_equivalence_detected_with_economics_scaling():
    specs=(CandidateSpec("a",1,instrument_id="X",unit_quantity=Decimal("1"),entry_cost=Decimal("250"),maximum_loss=Decimal("250"),margin=Decimal("250"),canonical_candidate_id="canon",p5_variant="same"),
           CandidateSpec("b",2,instrument_id="X",unit_quantity=Decimal("2"),entry_cost=Decimal("500"),maximum_loss=Decimal("500"),margin=Decimal("500"),canonical_candidate_id="canon",p5_variant="same"))
    bundle,context=build_input(specs)
    group=run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups[0]
    assert group.equivalence_type is EquivalenceType.SCALE_EQUIVALENT
    assert group.members[1].scale_factor_from_representative==2


def test_cost_mismatch_prevents_hard_equivalence():
    specs=(CandidateSpec("a",1,instrument_id="X",entry_cost=Decimal("250")),CandidateSpec("b",2,instrument_id="X",entry_cost=Decimal("251")))
    bundle,context=build_input(specs)
    assert run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups==()


def test_soft_similarity_request_has_no_exclusion_authority():
    specs=(CandidateSpec("a",1,instrument_id="X"),CandidateSpec("b",2,instrument_id="Y"))
    bundle,context=build_input(specs)
    requests=run_s2(S2RunRequest(bundle,context)).m03.soft_similarity_requests.requests
    assert requests and all(request.exclusion_authority is False for request in requests)
