
from decimal import Decimal

from quant_pipeline.phase_08_contracts.enums import ConfidenceState,ScoreSemantics
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import ConfidenceEvidenceState,PairwiseMode
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.policies import OrdinalPreferencePolicy,S2Policy
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_adjacent_tiers_compile_only_adjacent_constraints():
    specs=(CandidateSpec("a",1),CandidateSpec("b",2,instrument_id="Y"),CandidateSpec("c",3,instrument_id="Z"))
    bundle,context=build_input(specs)
    prefs=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences
    assert {(x.preferred_candidate_id,x.less_preferred_candidate_id) for x in prefs.pairwise_constraints}=={("a","b"),("b","c")}


def test_all_tiers_mode_compiles_transitive_pairs():
    specs=(CandidateSpec("a",1),CandidateSpec("b",2,instrument_id="Y"),CandidateSpec("c",3,instrument_id="Z"))
    bundle,context=build_input(specs)
    policy=S2Policy(ordinal=OrdinalPreferencePolicy(pairwise_mode=PairwiseMode.ALL_ORDERED_TIERS))
    prefs=run_s2(S2RunRequest(bundle,context),policy=policy).m06.ordinal_preferences
    assert len(prefs.pairwise_constraints)==3


def test_tied_rank_forms_one_lexicographic_tier_without_pairwise_order_between_ties():
    specs=(CandidateSpec("a",1),CandidateSpec("b",1,instrument_id="Y"),CandidateSpec("c",2,instrument_id="Z"))
    bundle,context=build_input(specs)
    prefs=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences
    assert prefs.lexicographic_tiers[0].candidate_ids==("a","b")
    assert all({x.preferred_candidate_id,x.less_preferred_candidate_id}!={"a","b"} for x in prefs.pairwise_constraints)


def test_cross_group_constraints_are_never_generated():
    specs=(CandidateSpec("a",1,group_id="g1"),CandidateSpec("b",1,group_id="g2",instrument_id="Y"))
    bundle,context=build_input(specs)
    prefs=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences
    assert prefs.pairwise_constraints==()
    assert prefs.proof.cross_group_constraints_absent is True


def test_cardinal_score_is_not_consumed():
    specs=(CandidateSpec("a",1,score_semantics=ScoreSemantics.CARDINAL_WITHIN_GROUP,score_value=Decimal("9"),confidence_state=ConfidenceState.CALIBRATED),)
    bundle,context=build_input(specs)
    prefs=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences
    assert "CARDINAL_SCORE_VALUE_NOT_CONSUMED_BY_S2" in prefs.reason_codes
    assert prefs.proof.score_values_ignored is True
    assert prefs.proof.cardinal_financial_outputs_absent is True
    assert prefs.proof.scenario_distribution_unchanged is True


def test_calibrated_confidence_produces_reference_hint_not_numeric_cap():
    specs=(CandidateSpec("a",1,confidence_state=ConfidenceState.CALIBRATED,score_semantics=ScoreSemantics.ORDINAL),)
    bundle,context=build_input(specs)
    hint=run_s2(S2RunRequest(bundle,context)).m06.ordinal_preferences.confidence_hints[0]
    assert hint.state is ConfidenceEvidenceState.CALIBRATED_REFERENCE_AVAILABLE
    assert hint.numerical_cap_status=="NOT_DERIVED_BY_S2"
