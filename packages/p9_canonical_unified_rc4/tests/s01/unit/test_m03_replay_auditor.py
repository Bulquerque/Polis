from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.replay import (
    OrderedEventLedger,
    OrderedEventLedgerPayload,
    ReplayCheckpoint,
    ReplayCheckpointPayload,
    ReplayEvent,
    ReplayEventType,
    ReplayIntegrityStatus,
    ReplayPolicy,
    ReplayState,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m03_replay_auditor import (
    DeterministicReplayIntegrityAuditor,
)


def _envelope(payload):
    return IntegrityEnvelope(payload_sha256=payload_sha256(payload))


def test_empty_no_action_replay_is_exact() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = ReplayState(as_of=now, cash=Decimal("100"))
    checkpoint_payload = ReplayCheckpointPayload(
        checkpoint_id="cp",
        last_sequence=-1,
        state=state,
    )
    ledger_payload = OrderedEventLedgerPayload(ledger_id="ledger", events=())
    result = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(payload=ledger_payload, integrity=_envelope(ledger_payload)),
        expected_state=state,
        policy=ReplayPolicy(),
    )
    assert result.report.status is ReplayIntegrityStatus.REPLAY_EXACT


def test_non_contiguous_event_stream_is_invalid() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = ReplayState(as_of=now, cash=Decimal("100"))
    checkpoint_payload = ReplayCheckpointPayload(checkpoint_id="cp", last_sequence=-1, state=state)
    event = ReplayEvent(
        event_id="e2",
        sequence=2,
        occurred_at=now + timedelta(seconds=1),
        event_type=ReplayEventType.CASH_ADJUSTMENT,
        cash_amount=Decimal("1"),
    )
    ledger_payload = OrderedEventLedgerPayload(ledger_id="ledger", events=(event,))
    result = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(payload=ledger_payload, integrity=_envelope(ledger_payload)),
        expected_state=state,
        policy=ReplayPolicy(require_contiguous_sequence=True),
    )
    assert result.report.status is ReplayIntegrityStatus.EVENT_STREAM_INVALID
    assert result.exceptions.exceptions


def test_replay_detects_cash_divergence(full_fixture) -> None:
    from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import P8EvaluationHandoffValidator
    from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.runner import S1Runner

    validated = P8EvaluationHandoffValidator(
        compatibility=full_fixture.compatibility,
        module_registry=full_fixture.module_registry,
        schema_registry=full_fixture.schema_registry,
        artifact_store=full_fixture.store,
    ).validate(full_fixture.handoff).validated
    assert validated is not None
    runner = S1Runner(
        artifact_store=full_fixture.store,
        compatibility=full_fixture.compatibility,
        module_registry=full_fixture.module_registry,
        schema_registry=full_fixture.schema_registry,
        clock=full_fixture.clock,
    )
    checkpoint = runner._parse_role(validated, "replay_checkpoint_manifest", ReplayCheckpoint)
    ledger = runner._parse_role(validated, "ordered_event_ledger", OrderedEventLedger)
    expected = ReplayState(as_of=full_fixture.evaluation_as_of, cash=Decimal("999"))
    result = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=checkpoint,
        event_ledger=ledger,
        expected_state=expected,
        policy=ReplayPolicy(),
    )
    assert result.report.status is ReplayIntegrityStatus.REPLAY_DIVERGED
    assert any(item.field == "cash" for item in result.report.differences)


def test_invalid_checkpoint_and_ledger_integrity_are_rejected() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = ReplayState(as_of=now, cash=Decimal("100"))
    checkpoint_payload = ReplayCheckpointPayload(checkpoint_id="cp", last_sequence=-1, state=state)
    ledger_payload = OrderedEventLedgerPayload(ledger_id="ledger", events=())
    auditor = DeterministicReplayIntegrityAuditor()

    bad_checkpoint = auditor.audit(
        checkpoint=ReplayCheckpoint(
            payload=checkpoint_payload,
            integrity=IntegrityEnvelope(payload_sha256="f" * 64),
        ),
        event_ledger=OrderedEventLedger(payload=ledger_payload, integrity=_envelope(ledger_payload)),
        expected_state=state,
        policy=ReplayPolicy(),
    )
    assert bad_checkpoint.report.status is ReplayIntegrityStatus.CHECKPOINT_INVALID

    bad_ledger = auditor.audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(
            payload=ledger_payload,
            integrity=IntegrityEnvelope(payload_sha256="f" * 64),
        ),
        expected_state=state,
        policy=ReplayPolicy(),
    )
    assert bad_ledger.report.status is ReplayIntegrityStatus.EVENT_STREAM_INVALID


def test_replay_applies_fee_cash_adjustment_and_settlement() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = ReplayState(as_of=now, cash=Decimal("1000"))
    checkpoint_payload = ReplayCheckpointPayload(checkpoint_id="cp", last_sequence=-1, state=state)
    events = (
        ReplayEvent(
            event_id="fill",
            sequence=0,
            occurred_at=now + timedelta(seconds=1),
            event_type=ReplayEventType.FILL,
            fill_id="f1",
            position_id="p1",
            candidate_id="c1",
            instrument_id="i1",
            quantity_delta=Decimal("2"),
            price=Decimal("100"),
            fee_amount=Decimal("1"),
        ),
        ReplayEvent(
            event_id="fee",
            sequence=1,
            occurred_at=now + timedelta(seconds=2),
            event_type=ReplayEventType.FEE,
            fee_amount=Decimal("2"),
        ),
        ReplayEvent(
            event_id="cash",
            sequence=2,
            occurred_at=now + timedelta(seconds=3),
            event_type=ReplayEventType.CASH_ADJUSTMENT,
            cash_amount=Decimal("10"),
        ),
        ReplayEvent(
            event_id="settle",
            sequence=3,
            occurred_at=now + timedelta(seconds=4),
            event_type=ReplayEventType.SETTLEMENT,
            position_id="p1",
            settlement_cash=Decimal("220"),
        ),
    )
    ledger_payload = OrderedEventLedgerPayload(ledger_id="ledger", events=events)
    expected = ReplayState(
        as_of=now + timedelta(seconds=4),
        cash=Decimal("1027"),
        fees_paid=Decimal("3"),
    )
    result = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(payload=ledger_payload, integrity=_envelope(ledger_payload)),
        expected_state=expected,
        policy=ReplayPolicy(),
    )
    assert result.report.status is ReplayIntegrityStatus.REPLAY_EXACT


def test_duplicate_event_id_and_unknown_mark_are_invalid() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = ReplayState(as_of=now, cash=Decimal("100"))
    checkpoint_payload = ReplayCheckpointPayload(checkpoint_id="cp", last_sequence=-1, state=state)
    out_of_order_events = (
        ReplayEvent(
            event_id="later",
            sequence=1,
            occurred_at=now + timedelta(seconds=1),
            event_type=ReplayEventType.CASH_ADJUSTMENT,
            cash_amount=Decimal("1"),
        ),
        ReplayEvent(
            event_id="earlier",
            sequence=0,
            occurred_at=now + timedelta(seconds=2),
            event_type=ReplayEventType.CASH_ADJUSTMENT,
            cash_amount=Decimal("1"),
        ),
    )
    out_of_order_payload = OrderedEventLedgerPayload(ledger_id="order", events=out_of_order_events)
    out_of_order = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(
            payload=out_of_order_payload, integrity=_envelope(out_of_order_payload)
        ),
        expected_state=state,
        policy=ReplayPolicy(),
    )
    assert "P9_S1_REPLAY_EVENT_ORDER_INVALID" in out_of_order.report.reason_codes

    mark_event = ReplayEvent(
        event_id="mark",
        sequence=0,
        occurred_at=now + timedelta(seconds=1),
        event_type=ReplayEventType.MARK,
        position_id="unknown",
        mark_price=Decimal("10"),
    )
    mark_payload = OrderedEventLedgerPayload(ledger_id="mark-ledger", events=(mark_event,))
    bad_mark = DeterministicReplayIntegrityAuditor().audit(
        checkpoint=ReplayCheckpoint(payload=checkpoint_payload, integrity=_envelope(checkpoint_payload)),
        event_ledger=OrderedEventLedger(payload=mark_payload, integrity=_envelope(mark_payload)),
        expected_state=state,
        policy=ReplayPolicy(),
    )
    assert bad_mark.report.status is ReplayIntegrityStatus.EVENT_STREAM_INVALID
    assert bad_mark.exceptions.exceptions[0].reason_code == "P9_S1_REPLAY_EVENT_INVALID"
