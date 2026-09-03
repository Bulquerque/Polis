from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.integrity_models import (
    CandidateTerminalRecord,
    CandidateTerminalState,
    QualificationState,
)
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m04_integrity_replay import (
    finalize_handoff_replay_hash,
    qualify_backtest,
)

from tests.s03.conftest import no_action_handoff, valid_trade_handoff


def rebuild(handoff, **updates):
    data = handoff.model_dump(mode="python")
    data.update(updates)
    data["replay_sha256"] = "0" * 64
    return finalize_handoff_replay_hash(type(handoff).model_validate(data))


def test_valid_trade_is_qualified():
    receipt = qualify_backtest(valid_trade_handoff())
    assert receipt.state is QualificationState.QUALIFIED
    assert all(check.passed for check in receipt.checks)
    assert receipt.qualified_handoff_sha256 is not None


def test_legitimate_no_action_is_preserved():
    receipt = qualify_backtest(no_action_handoff())
    assert receipt.state is QualificationState.NO_ACTION_VALID
    assert receipt.reason_codes == ()


def test_candidate_disappearance_invalidates_backtest():
    handoff = valid_trade_handoff()
    broken = rebuild(handoff, p7_terminal_records=())
    receipt = qualify_backtest(broken)
    assert receipt.state is QualificationState.INVALID
    assert "P9_S3_CANDIDATE_CONSERVATION_FAILED" in receipt.reason_codes


def test_blocked_candidate_cannot_be_executed():
    handoff = valid_trade_handoff()
    broken = rebuild(
        handoff,
        p7_terminal_records=(
            CandidateTerminalRecord(candidate_id="candidate-1", state=CandidateTerminalState.BLOCKED),
        ),
    )
    receipt = qualify_backtest(broken)
    assert receipt.state is QualificationState.INVALID
    assert "P9_S3_CANDIDATE_CONSERVATION_FAILED" in receipt.reason_codes


def test_overfill_is_rejected():
    handoff = valid_trade_handoff()
    fill = handoff.fills[0].model_copy(update={"quantity": Decimal("3")})
    broken = rebuild(handoff, fills=(fill,))
    receipt = qualify_backtest(broken)
    assert "P9_S3_ORDER_FILL_MISMATCH" in receipt.reason_codes


def test_cash_mismatch_is_rejected():
    handoff = valid_trade_handoff()
    broken = rebuild(handoff, end_cash=Decimal("80"))
    receipt = qualify_backtest(broken)
    assert "P9_S3_ACCOUNTING_MISMATCH" in receipt.reason_codes


def test_position_mismatch_is_rejected():
    handoff = valid_trade_handoff()
    position = handoff.final_positions[0].model_copy(update={"quantity": Decimal("1")})
    broken = rebuild(handoff, final_positions=(position,))
    receipt = qualify_backtest(broken)
    assert "P9_S3_POSITION_RECONCILIATION_FAILED" in receipt.reason_codes


def test_missing_lifecycle_support_is_blocking():
    handoff = valid_trade_handoff()
    broken = rebuild(handoff, required_lifecycle_supported=False)
    receipt = qualify_backtest(broken)
    assert "P9_S3_LIFECYCLE_UNSUPPORTED" in receipt.reason_codes


def test_replay_hash_mismatch_is_blocking():
    handoff = valid_trade_handoff().model_copy(update={"replay_sha256": "f" * 64})
    receipt = qualify_backtest(handoff)
    assert "P9_S3_REPLAY_DIVERGED" in receipt.reason_codes


def test_legacy_handoff_is_never_qualified():
    handoff = rebuild(valid_trade_handoff(), capability="LEGACY_RESEARCH_ONLY")
    receipt = qualify_backtest(handoff)
    assert receipt.state is QualificationState.LEGACY_RESEARCH_ONLY
    assert "P9_S3_LEGACY_P8_NOT_QUALIFIABLE" in receipt.reason_codes
