from __future__ import annotations

from .errors import ReplayError

from dataclasses import dataclass
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import payload_sha256, verify_integrity
from quant_pipeline.phase_09.contracts.replay import (
    OrderedEventLedger,
    PositionState,
    ReconstructedStateHashPanel,
    ReplayCheckpoint,
    ReplayDifference,
    ReplayEvent,
    ReplayEventType,
    ReplayExceptionPanel,
    ReplayExceptionRecord,
    ReplayIntegrityReport,
    ReplayIntegrityStatus,
    ReplayPolicy,
    ReplayState,
)


@dataclass(frozen=True, slots=True)
class ReplayAuditOutcome:
    report: ReplayIntegrityReport
    hashes: ReconstructedStateHashPanel
    exceptions: ReplayExceptionPanel


class DeterministicReplayIntegrityAuditor:
    module_id = "P9.S1.M03"

    def audit(
        self,
        *,
        checkpoint: ReplayCheckpoint,
        event_ledger: OrderedEventLedger,
        expected_state: ReplayState,
        policy: ReplayPolicy,
    ) -> ReplayAuditOutcome:
        checkpoint_hash = payload_sha256(checkpoint.payload)
        ledger_hash = payload_sha256(event_ledger.payload)
        empty_hashes = ReconstructedStateHashPanel(
            checkpoint_sha256=checkpoint_hash,
            event_ledger_sha256=ledger_hash,
            reconstructed_state_sha256=None,
            expected_state_sha256=payload_sha256(expected_state),
        )
        if not verify_integrity(checkpoint.payload, checkpoint.integrity):
            report = ReplayIntegrityReport(
                status=ReplayIntegrityStatus.CHECKPOINT_INVALID,
                event_count=len(event_ledger.payload.events),
                reconstructed_state=None,
                expected_state=expected_state,
                reason_codes=("P9_S1_REPLAY_CHECKPOINT_INVALID",),
            )
            return ReplayAuditOutcome(report, empty_hashes, ReplayExceptionPanel())
        if not verify_integrity(event_ledger.payload, event_ledger.integrity):
            report = ReplayIntegrityReport(
                status=ReplayIntegrityStatus.EVENT_STREAM_INVALID,
                event_count=len(event_ledger.payload.events),
                reconstructed_state=None,
                expected_state=expected_state,
                reason_codes=("P9_S1_REPLAY_EVENT_STREAM_HASH_MISMATCH",),
            )
            return ReplayAuditOutcome(report, empty_hashes, ReplayExceptionPanel())

        events = list(event_ledger.payload.events)
        exceptions = self._validate_event_order(
            events,
            checkpoint.payload.last_sequence,
            policy.require_contiguous_sequence,
        )
        if exceptions:
            report = ReplayIntegrityReport(
                status=ReplayIntegrityStatus.EVENT_STREAM_INVALID,
                event_count=len(events),
                reconstructed_state=None,
                expected_state=expected_state,
                reason_codes=tuple(sorted({item.reason_code for item in exceptions})),
            )
            return ReplayAuditOutcome(
                report,
                empty_hashes,
                ReplayExceptionPanel(exceptions=tuple(exceptions)),
            )

        state = checkpoint.payload.state
        try:
            for event in events:
                if event.sequence <= checkpoint.payload.last_sequence:
                    continue
                state = self._apply_event(state, event)
        except ValueError as exc:
            exception = ReplayExceptionRecord(
                event_id=event.event_id,
                sequence=event.sequence,
                reason_code="P9_S1_REPLAY_EVENT_INVALID",
                message=str(exc),
            )
            report = ReplayIntegrityReport(
                status=ReplayIntegrityStatus.EVENT_STREAM_INVALID,
                event_count=len(events),
                reconstructed_state=None,
                expected_state=expected_state,
                reason_codes=(exception.reason_code,),
            )
            return ReplayAuditOutcome(
                report,
                empty_hashes,
                ReplayExceptionPanel(exceptions=(exception,)),
            )

        differences = self._differences(state, expected_state, policy.accounting_tolerance)
        exact = payload_sha256(state) == payload_sha256(expected_state)
        numerically_equivalent = not differences
        if exact:
            status = ReplayIntegrityStatus.REPLAY_EXACT
            reason_codes: tuple[str, ...] = ()
        elif numerically_equivalent and policy.allow_numerical_equivalence:
            status = ReplayIntegrityStatus.REPLAY_NUMERICALLY_EQUIVALENT
            reason_codes = ()
        else:
            status = ReplayIntegrityStatus.REPLAY_DIVERGED
            reason_codes = tuple(sorted({difference.reason_code for difference in differences}))
        report = ReplayIntegrityReport(
            status=status,
            event_count=len(events),
            reconstructed_state=state,
            expected_state=expected_state,
            differences=tuple(differences),
            reason_codes=reason_codes,
        )
        hashes = ReconstructedStateHashPanel(
            checkpoint_sha256=checkpoint_hash,
            event_ledger_sha256=ledger_hash,
            reconstructed_state_sha256=payload_sha256(state),
            expected_state_sha256=payload_sha256(expected_state),
        )
        return ReplayAuditOutcome(report, hashes, ReplayExceptionPanel())

    @staticmethod
    def _validate_event_order(
        events: list[ReplayEvent],
        last_sequence: int,
        require_contiguous: bool,
    ) -> list[ReplayExceptionRecord]:
        exceptions: list[ReplayExceptionRecord] = []
        seen_ids: set[str] = set()
        previous_sequence = last_sequence
        for event in events:
            if event.event_id in seen_ids:
                exceptions.append(
                    ReplayExceptionRecord(
                        event_id=event.event_id,
                        sequence=event.sequence,
                        reason_code="P9_S1_REPLAY_DUPLICATE_EVENT",
                        message="duplicate event ID",
                    )
                )
            seen_ids.add(event.event_id)
            if event.sequence <= previous_sequence:
                exceptions.append(
                    ReplayExceptionRecord(
                        event_id=event.event_id,
                        sequence=event.sequence,
                        reason_code="P9_S1_REPLAY_EVENT_ORDER_INVALID",
                        message="event sequence is not strictly increasing",
                    )
                )
            if require_contiguous and event.sequence > last_sequence:
                if event.sequence != previous_sequence + 1:
                    exceptions.append(
                        ReplayExceptionRecord(
                            event_id=event.event_id,
                            sequence=event.sequence,
                            reason_code="P9_S1_REPLAY_EVENT_ORDER_INVALID",
                            message="event sequence is not contiguous",
                        )
                    )
            previous_sequence = max(previous_sequence, event.sequence)
        return exceptions

    def _apply_event(self, state: ReplayState, event: ReplayEvent) -> ReplayState:
        positions = {position.position_id: position for position in state.positions}
        cash = state.cash
        fees = state.fees_paid
        margin = state.margin_used

        if event.event_type is ReplayEventType.FILL:
            if (
                event.position_id is None
                or event.candidate_id is None
                or event.instrument_id is None
                or event.price is None
            ):
                raise ReplayError("FILL event lacks required position/candidate/instrument/price")
            current = positions.get(event.position_id)
            if current is None:
                current = PositionState(
                    position_id=event.position_id,
                    candidate_id=event.candidate_id,
                    instrument_id=event.instrument_id,
                    quantity=Decimal("0"),
                    mark_price=event.price,
                    contract_multiplier=event.contract_multiplier,
                )
            if current.instrument_id != event.instrument_id:
                raise ValueError("position instrument mismatch")
            quantity = current.quantity + event.quantity_delta
            positions[event.position_id] = current.model_copy(
                update={"quantity": quantity, "mark_price": event.price}
            )
            cash -= event.quantity_delta * event.price * event.contract_multiplier
            cash -= event.fee_amount
            fees += event.fee_amount
        elif event.event_type is ReplayEventType.FEE:
            cash -= event.fee_amount
            fees += event.fee_amount
        elif event.event_type is ReplayEventType.MARK:
            if event.position_id is None or event.mark_price is None:
                raise ReplayError("MARK event lacks position_id or mark_price")
            current = positions.get(event.position_id)
            if current is None:
                raise ValueError("mark references unknown position")
            positions[event.position_id] = current.model_copy(
                update={"mark_price": event.mark_price}
            )
        elif event.event_type is ReplayEventType.MARGIN_UPDATE:
            if event.margin_used is None:
                raise ReplayError("MARGIN_UPDATE event lacks margin_used")
            margin = event.margin_used
        elif event.event_type is ReplayEventType.CASH_ADJUSTMENT:
            if event.cash_amount is None:
                raise ReplayError("CASH_ADJUSTMENT event lacks cash_amount")
            cash += event.cash_amount
        elif event.event_type is ReplayEventType.SETTLEMENT:
            if event.position_id is None or event.settlement_cash is None:
                raise ReplayError("SETTLEMENT event lacks position_id or settlement_cash")
            current = positions.get(event.position_id)
            if current is None:
                raise ValueError("settlement references unknown position")
            cash += event.settlement_cash
            positions[event.position_id] = current.model_copy(update={"quantity": Decimal("0")})

        active_positions = tuple(
            sorted(
                (position for position in positions.values() if position.quantity != 0),
                key=lambda position: position.position_id,
            )
        )
        return ReplayState(
            as_of=event.occurred_at,
            cash=cash,
            margin_used=margin,
            fees_paid=fees,
            positions=active_positions,
        )

    @staticmethod
    def _differences(
        observed: ReplayState,
        expected: ReplayState,
        tolerance: Decimal,
    ) -> list[ReplayDifference]:
        differences: list[ReplayDifference] = []
        for field, observed_value, expected_value, code in (
            ("cash", observed.cash, expected.cash, "P9_S1_REPLAY_CASH_DIVERGENCE"),
            (
                "margin_used",
                observed.margin_used,
                expected.margin_used,
                "P9_S1_REPLAY_MARGIN_DIVERGENCE",
            ),
            (
                "fees_paid",
                observed.fees_paid,
                expected.fees_paid,
                "P9_S1_REPLAY_PNL_DIVERGENCE",
            ),
            ("nav", observed.nav, expected.nav, "P9_S1_REPLAY_PNL_DIVERGENCE"),
        ):
            delta = abs(observed_value - expected_value)
            if delta > tolerance:
                differences.append(
                    ReplayDifference(
                        field=field,
                        expected=str(expected_value),
                        observed=str(observed_value),
                        absolute_difference=delta,
                        reason_code=code,
                    )
                )
        observed_positions = {position.position_id: position for position in observed.positions}
        expected_positions = {position.position_id: position for position in expected.positions}
        if observed_positions.keys() != expected_positions.keys():
            differences.append(
                ReplayDifference(
                    field="positions.keys",
                    expected=repr(sorted(expected_positions)),
                    observed=repr(sorted(observed_positions)),
                    reason_code="P9_S1_REPLAY_POSITION_DIVERGENCE",
                )
            )
            return differences
        for position_id, observed_position in observed_positions.items():
            expected_position = expected_positions[position_id]
            for field in ("quantity", "mark_price", "contract_multiplier"):
                observed_value = getattr(observed_position, field)
                expected_value = getattr(expected_position, field)
                delta = abs(observed_value - expected_value)
                if delta > tolerance:
                    differences.append(
                        ReplayDifference(
                            field=f"positions.{position_id}.{field}",
                            expected=str(expected_value),
                            observed=str(observed_value),
                            absolute_difference=delta,
                            reason_code="P9_S1_REPLAY_POSITION_DIVERGENCE",
                        )
                    )
        return differences
