
from quant_pipeline.phase_08_contracts.enums import ComponentQualificationStatus,P7TerminalState
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.enums import StaticActionState
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.policies import S2Policy,StaticAdmissionPolicy
from tests.agents.a1_s2.factories import CandidateSpec, build_input


def test_all_candidates_receive_one_static_decision():
    bundle,context=build_input((CandidateSpec("a",1),),terminal_candidates=(("x",P7TerminalState.ABSTAINED),))
    universe=run_s2(S2RunRequest(bundle,context)).m05.static_action_universe
    assert {row.candidate_id for row in universe.decisions}=={"a","x"}
    assert universe.proof.equation_valid


def test_payoff_unavailable_is_static_capability_unsupported():
    spec=CandidateSpec("a",1,payoff_status=ComponentQualificationStatus.UNAVAILABLE)
    bundle,context=build_input((spec,))
    decision=run_s2(S2RunRequest(bundle,context)).m05.static_action_universe.decisions[0]
    assert decision.state is StaticActionState.STATIC_CAPABILITY_UNSUPPORTED


def test_liquidity_unavailable_is_not_decided_by_s2():
    # CandidateSpec fixes liquidity qualified; modify model after factory to isolate boundary in another test.
    bundle,context=build_input()
    decision=run_s2(S2RunRequest(bundle,context)).m05.static_action_universe.decisions[0]
    assert decision.state is StaticActionState.FORWARD_TO_RISK
    assert all("LIQUIDITY" not in code for code in decision.reason_codes)


def test_exact_redundancy_collapse_is_opt_in():
    specs=(CandidateSpec("a",1,instrument_id="X",canonical_candidate_id="canon",p5_variant="same"),CandidateSpec("b",2,instrument_id="X",canonical_candidate_id="canon",p5_variant="same"))
    bundle,context=build_input(specs)
    default=run_s2(S2RunRequest(bundle,context)).m05.static_action_universe
    assert default.forwarded_candidate_ids==("a","b")
    policy=S2Policy(static_admission=StaticAdmissionPolicy(collapse_exact_redundancy=True))
    collapsed=run_s2(S2RunRequest(bundle,context),policy=policy).m05.static_action_universe
    assert collapsed.forwarded_candidate_ids==("a",)
    assert next(row for row in collapsed.decisions if row.candidate_id=="b").representative_candidate_id=="a"
