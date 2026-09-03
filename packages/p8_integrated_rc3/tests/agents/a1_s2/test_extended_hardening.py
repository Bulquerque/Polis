from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, finalize_content_hash
from quant_pipeline.phase_08_contracts.enums import (
    ComponentQualificationStatus, ConfidenceState, ExerciseStyle, PositionSide, SettlementType,
)
from quant_pipeline.phase_08_contracts.p6 import CandidateLegV1
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import StaticActionState
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.equivalence import EquivalenceGroup, EquivalenceMember
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.graph import ExposureEdge, ExposureNode, GraphComponent, StructuralExposureGraph
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.netting import (
    CandidateInstrumentCoefficient, NettingTransform, NettingTransformProof, VirtualCandidateIntentRecord,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.preferences import (
    OrdinalPenaltyTemplate, OrdinalPreferenceConstraintSet, OrdinalSemanticsProof, PairwiseOrdinalConstraint,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.universe import (
    StaticActionDecision, StaticAdmissibleActionUniverse, StaticUniverseConservationProof,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import (
    EquivalenceType, ExposureNodeType, ExposureRelationType, OrdinalConstraintType, PairwiseMode,
    VirtualIntentState,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.errors import (
    CandidateNormalizationError, GraphIntegrityError, NettingIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.policies import EquivalencePolicy, S2Policy
from tests.agents.a1_s2.factories import CandidateSpec, BASE, build_input, ref, replace_candidate_package, replace_validated_handoff


def test_unresolved_evidence_is_rejected_by_normalizer():
    from quant_pipeline.phase_08_contracts.enums import EvidenceResolutionStatus
    bundle,context=build_input()
    row=bundle.resolved_evidence.candidates[0].model_copy(update={"status":EvidenceResolutionStatus.UNAVAILABLE})
    index=bundle.resolved_evidence.model_copy(update={"candidates":(row,)})
    snapshot=finalize_content_hash(bundle.snapshot.model_copy(update={"resolved_evidence_hash":canonical_sha256(index)}))
    broken=finalize_content_hash(bundle.model_copy(update={"resolved_evidence":index,"snapshot":snapshot}))
    with pytest.raises(CandidateNormalizationError,match="not resolved"):
        run_s2(S2RunRequest(broken,context))


def test_missing_p6_payload_is_rejected():
    bundle,context=build_input()
    row=bundle.resolved_evidence.candidates[0].model_copy(update={"p6_package":None})
    index=bundle.resolved_evidence.model_copy(update={"candidates":(row,)})
    snapshot=finalize_content_hash(bundle.snapshot.model_copy(update={"resolved_evidence_hash":canonical_sha256(index)}))
    broken=finalize_content_hash(bundle.model_copy(update={"resolved_evidence":index,"snapshot":snapshot}))
    with pytest.raises(CandidateNormalizationError,match="lacks P6/P5"):
        run_s2(S2RunRequest(broken,context))


def test_p6_p7_identity_mismatch_is_rejected():
    bundle,context=build_input()
    package=bundle.resolved_evidence.candidates[0].p6_package.model_copy(update={"canonical_candidate_id":"other"})
    broken=replace_candidate_package(bundle,"cand-1",package)
    with pytest.raises(CandidateNormalizationError,match="identity mismatch"):
        run_s2(S2RunRequest(broken,context))


def test_missing_comparison_group_is_rejected_by_graph():
    bundle,context=build_input()
    handoff=bundle.validated_handoff.handoff.model_copy(update={"comparison_groups":()})
    broken=replace_validated_handoff(bundle,handoff)
    with pytest.raises(GraphIntegrityError,match="comparison group"):
        run_s2(S2RunRequest(broken,context))


def test_graph_components_do_not_connect_unrelated_candidates_only_by_currency():
    specs=(CandidateSpec("a",1,group_id="g1",instrument_id="X",underlying="A",objective_family="O1"),
           CandidateSpec("b",1,group_id="g2",instrument_id="Y",underlying="B",objective_family="O2",expiration_days=60))
    bundle,context=build_input(specs)
    graph=run_s2(S2RunRequest(bundle,context)).m02.exposure_graph
    candidate_components={node_id:component.component_id for component in graph.connected_components for node_id in component.node_ids if node_id.startswith("candidate:")}
    assert candidate_components["candidate:a"] != candidate_components["candidate:b"]


def test_cross_group_equivalence_is_never_hard_by_default():
    specs=(CandidateSpec("a",1,group_id="g1",instrument_id="X",canonical_candidate_id="canon",p5_variant="same"),
           CandidateSpec("b",1,group_id="g2",instrument_id="X",canonical_candidate_id="canon",p5_variant="same"))
    bundle,context=build_input(specs)
    group=run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups[0]
    assert not group.hard_redundant_eligible
    assert "CROSS_GROUP_PHYSICAL_EQUIVALENCE_NOT_REDUNDANT" in group.reason_codes


def test_equivalence_policy_can_relax_p5_requirement_explicitly():
    specs=(CandidateSpec("a",1,instrument_id="X",canonical_candidate_id="canon",p5_variant="one"),
           CandidateSpec("b",2,instrument_id="X",canonical_candidate_id="canon",p5_variant="two"))
    bundle,context=build_input(specs)
    policy=S2Policy(equivalence=EquivalencePolicy(require_same_p5_belief_for_hard_redundancy=False))
    group=run_s2(S2RunRequest(bundle,context),policy=policy).m03.equivalence_groups.groups[0]
    assert group.hard_redundant_eligible
    assert "DIFFERENT_P5_EVIDENCE_SIGNATURE" in group.reason_codes


def test_opposite_legs_are_not_scale_equivalent():
    specs=(CandidateSpec("a",1,instrument_id="X",side=PositionSide.LONG),CandidateSpec("b",2,instrument_id="X",side=PositionSide.SHORT))
    bundle,context=build_input(specs)
    assert run_s2(S2RunRequest(bundle,context)).m03.equivalence_groups.groups==()


def test_lifecycle_unavailable_is_static_unsupported():
    spec=CandidateSpec("a",1,lifecycle_status=ComponentQualificationStatus.UNAVAILABLE)
    bundle,context=build_input((spec,))
    decision=run_s2(S2RunRequest(bundle,context)).m05.static_action_universe.decisions[0]
    assert decision.state is StaticActionState.STATIC_CAPABILITY_UNSUPPORTED
    assert decision.reason_codes==("LIFECYCLE_CAPABILITY_UNUSABLE",)


def test_unavailable_confidence_creates_no_numeric_cap():
    spec=CandidateSpec("a",1,confidence_state=ConfidenceState.UNAVAILABLE)
    bundle,context=build_input((spec,))
    hint=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences.confidence_hints[0]
    assert hint.state.value=="UNAVAILABLE"
    assert hint.calibration_artifact_hash is None


def test_zero_net_multileg_candidate_is_rejected():
    bundle,context=build_input()
    package=bundle.resolved_evidence.candidates[0].p6_package
    first=package.legs[0]
    second=CandidateLegV1(
        instrument_id=first.instrument_id,instrument_type=first.instrument_type,side=PositionSide.SHORT,
        unit_quantity=Decimal("1"),contract_multiplier=first.contract_multiplier,strike=first.strike,
        expiration=first.expiration,exercise_style=first.exercise_style,settlement_type=first.settlement_type,
        contract_valid_from=first.contract_valid_from,contract_valid_until=first.contract_valid_until,
        instrument_master_ref=first.instrument_master_ref,
    )
    package=package.model_copy(update={"legs":(first,second)})
    broken=replace_candidate_package(bundle,"cand-1",package)
    with pytest.raises(NettingIntegrityError,match="zero net physical exposure"):
        run_s2(S2RunRequest(broken,context))


def test_two_legs_same_instrument_same_direction_sum_coefficient():
    # Multiple unit legs may intentionally reference the same fungible physical instrument.
    # S2 aggregates their signed quantities into one symbolic coefficient; it still does not choose a target quantity.
    bundle,context=build_input()
    package=bundle.resolved_evidence.candidates[0].p6_package
    first=package.legs[0]
    second=first.model_copy(update={"strike":Decimal("110")})
    package=package.model_copy(update={"legs":(first,second)})
    broken=replace_candidate_package(bundle,"cand-1",package)
    result=run_s2(S2RunRequest(broken,context))
    coeff=result.m04.netting_transform.coefficients[0]
    assert coeff.signed_contracts_per_candidate_unit==2


def test_contract_equivalence_rejects_missing_representative():
    with pytest.raises(ValidationError):
        EquivalenceGroup(
            equivalence_group_id="g",equivalence_type=EquivalenceType.EXACT_PHYSICAL,
            representative_candidate_id="x",comparison_group_id="cg",
            members=(EquivalenceMember(candidate_id="a",scale_factor_from_representative=Decimal("1")),
                     EquivalenceMember(candidate_id="b",scale_factor_from_representative=Decimal("1"))),
            physical_signature_hash="0"*64,hard_redundant_eligible=False,
        )


def test_graph_contract_rejects_unknown_node_edge():
    node=ExposureNode(node_id="candidate:a",node_type=ExposureNodeType.CANDIDATE,label="a")
    edge=ExposureEdge(edge_id="e",source_node_id="candidate:a",target_node_id="instrument:x",
                      relation=ExposureRelationType.SAME_INSTRUMENT,instrument_id="x")
    with pytest.raises(ValidationError,match="unknown node"):
        StructuralExposureGraph(contract_version="P8_STRUCTURAL_EXPOSURE_GRAPH_V1",schema_version="1.0.0",
            snapshot_id="s",nodes=(node,),edges=(edge,),connected_components=(GraphComponent(component_id="c",node_ids=("candidate:a",)),),content_sha256="0"*64)


def test_graph_contract_rejects_candidate_leg_without_quantity():
    with pytest.raises(ValidationError,match="require instrument"):
        ExposureEdge(edge_id="e",source_node_id="a",target_node_id="b",relation=ExposureRelationType.CANDIDATE_HAS_LEG)


def test_netting_contract_rejects_unmapped_active_candidate():
    with pytest.raises(ValidationError,match="active virtual candidate"):
        NettingTransform(contract_version="P8_NETTING_TRANSFORM_V1",schema_version="1.0.0",snapshot_id="s",
            virtual_intents=(VirtualCandidateIntentRecord(candidate_id="a",canonical_candidate_id="ca",unit_definition="u",state=VirtualIntentState.ACTIVE_FOR_SIZING),),
            coefficients=(),current_positions=(),proof=NettingTransformProof(candidate_count=1,instrument_count=0,coefficient_count=0,
                all_active_candidates_mapped=False,equation_semantics="target_physical_quantity = current_physical_quantity + sum(coefficient * virtual_candidate_quantity)"),content_sha256="0"*64)


def test_netting_coefficient_rejects_zero():
    with pytest.raises(ValidationError,match="non-zero"):
        CandidateInstrumentCoefficient(candidate_id="a",instrument_id="x",signed_contracts_per_candidate_unit=Decimal("0"),contract_multiplier=Decimal("1"),currency="USD")


def test_universe_contract_rejects_forwarded_list_mismatch():
    decision=StaticActionDecision(candidate_id="a",state=StaticActionState.FORWARD_TO_RISK)
    proof=StaticUniverseConservationProof(input_candidate_count=1,decision_count=1,forwarded_count=1,terminal_preserved_count=0,excluded_count=0,
        input_ids_hash="0"*64,decision_ids_hash="0"*64,equation_valid=True)
    with pytest.raises(ValidationError,match="must match"):
        StaticAdmissibleActionUniverse(contract_version="P8_STATIC_ADMISSIBLE_ACTION_UNIVERSE_V1",schema_version="1.0.0",
            snapshot_id="s",forwarded_candidate_ids=(),decisions=(decision,),proof=proof,content_sha256="0"*64)


def test_pairwise_contract_rejects_reversed_rank_order():
    with pytest.raises(ValidationError,match="preferred rank"):
        PairwiseOrdinalConstraint(constraint_id="c",constraint_type=OrdinalConstraintType.PREFERRED_OVER,
            comparison_group_id="g",preferred_candidate_id="a",less_preferred_candidate_id="b",preferred_rank=2,less_preferred_rank=1)


def test_preference_contract_rejects_missing_penalty_template():
    constraint=PairwiseOrdinalConstraint(constraint_id="c",constraint_type=OrdinalConstraintType.PREFERRED_OVER,
        comparison_group_id="g",preferred_candidate_id="a",less_preferred_candidate_id="b",preferred_rank=1,less_preferred_rank=2)
    with pytest.raises(ValidationError,match="penalty template"):
        OrdinalPreferenceConstraintSet(contract_version="P8_ORDINAL_PREFERENCE_CONSTRAINT_SET_V1",schema_version="1.0.0",snapshot_id="s",
            pairwise_constraints=(constraint,),lexicographic_tiers=(),penalty_templates=(),confidence_hints=(),
            proof=OrdinalSemanticsProof(pairwise_mode=PairwiseMode.ADJACENT_TIERS),content_sha256="0"*64)
