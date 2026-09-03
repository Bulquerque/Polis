from __future__ import annotations

from quant_pipeline.phase_08_contracts.enums import ReceiptStatus
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import run_s1

from tests.agents.a1_s1.factories import full_fixture


def test_ranked_golden_thread_runs_all_six_modules() -> None:
    fixture = full_fixture(ranked=True, include_feedback=True)
    result = run_s1(fixture.request, fixture.ports)
    assert result.m01.receipt.status is ReceiptStatus.ACCEPTED
    assert result.m02.ledger.proof.equation_valid
    assert result.m03.evidence_index.candidates[0].p6_package is not None
    assert result.m04.feedback_context.applied_feedback
    assert result.m05.current_state.quality_report.status.value.startswith("USABLE")
    assert result.m06.snapshot.actionable_ranked_candidate_ids == ("cand-1",)
    assert len(result.m06.phase7_consumption_receipt.candidate_receipts) == 1


def test_no_action_golden_thread_preserves_state_and_candidate() -> None:
    fixture = full_fixture(ranked=False)
    result = run_s1(fixture.request, fixture.ports)
    assert result.m02.ledger.proof.abstained_count == 1
    assert result.m03.evidence_index.candidates[0].status.value == "UNAVAILABLE"
    assert result.snapshot.no_action is not None
    assert result.snapshot.no_action.preserved_portfolio_state_hash == result.snapshot.portfolio_state_hash
    receipt = result.m06.phase7_consumption_receipt.candidate_receipts[0]
    assert receipt.status is ReceiptStatus.PRESERVED_TERMINAL


def test_feedback_does_not_mutate_upstream_or_portfolio_state() -> None:
    without_feedback = full_fixture(ranked=True, include_feedback=False)
    with_feedback = full_fixture(ranked=True, include_feedback=True)
    result_a = run_s1(without_feedback.request, without_feedback.ports)
    result_b = run_s1(with_feedback.request, with_feedback.ports)
    assert result_a.m02.ledger == result_b.m02.ledger
    assert result_a.m03.evidence_index == result_b.m03.evidence_index
    assert result_a.m05.current_state == result_b.m05.current_state
    assert result_a.snapshot.feedback_context_hash != result_b.snapshot.feedback_context_hash
