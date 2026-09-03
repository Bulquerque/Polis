from __future__ import annotations

from quant_pipeline.phase_08_portfolio_control.foundation.hashing import content_sha256

from .enums import StatefulEventKind
from .errors import LifecycleIntegrityError
from .input_models import S8InputBundle
from .lifecycle_engine import apply_option_event, apply_split
from .position_store import (
    apply_fill,
    assert_dual_book,
    build_instrument_registry,
    initialize_positions,
    render_positions,
)
from .reallocation_engine import apply_virtual_reallocations
from .state_models import ExecutionStateBundle, PositionLifecycleBundle
from .timeline_models import OrderedEventQueue

MODULE_ID = "P8.S8.M03"

_OPTION_EVENT_KINDS = {
    StatefulEventKind.EXERCISE,
    StatefulEventKind.ASSIGNMENT,
    StatefulEventKind.EXPIRATION,
    StatefulEventKind.CASH_SETTLEMENT,
}


def execute(
    value: S8InputBundle,
    queue: OrderedEventQueue,
    execution: ExecutionStateBundle,
) -> PositionLifecycleBundle:
    instruments = build_instrument_registry(value)
    options = {item.instrument_id: item for item in value.option_contracts}
    physical, virtual = initialize_positions(value)
    transitions = []
    lifecycle = []
    settlements = []
    for fill in execution.fills:
        apply_fill(fill, instruments, physical, virtual, transitions)
    apply_virtual_reallocations(value, instruments, virtual, transitions)
    for envelope in queue.events:
        if envelope.kind in _OPTION_EVENT_KINDS:
            event = envelope.payload
            option = options.get(event.instrument_id)
            if option is None:
                raise LifecycleIntegrityError(
                    f"missing option contract spec: {event.instrument_id}"
                )
            apply_option_event(
                event, option, instruments, physical, virtual,
                transitions, lifecycle, settlements,
            )
        elif envelope.kind == StatefulEventKind.CORPORATE_ACTION:
            apply_split(
                envelope.payload, value, instruments, physical, virtual,
                transitions, lifecycle,
            )
    assert_dual_book(physical, virtual)
    physical_out, virtual_out = render_positions(value.valuation_time, physical, virtual)
    payload = {
        "physical_positions": physical_out,
        "virtual_positions": virtual_out,
        "transitions": tuple(transitions),
        "lifecycle_ledger": tuple(lifecycle),
        "settlements": tuple(settlements),
    }
    return PositionLifecycleBundle(**payload, content_sha256=content_sha256(payload))
