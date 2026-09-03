from datetime import timedelta
from decimal import Decimal

import pytest

from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus, RuntimeControlMode
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import RuntimeControlCommand
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine import m01_timeline, m02_execution_state
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.enums import StatefulEventKind
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.errors import LedgerIntegrityError, TimelineIntegrityError
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.sealing import seal_s8_input
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.timeline_models import OrderedEventQueue


def test_timeline_runtime_command_precedes_order(s8_linear_input):
    command = RuntimeControlCommand(
        command_id="cmd", event_time=s8_linear_input.decision_time,
        mode=RuntimeControlMode.HOLD_NO_NEW_RISK, reason_code="TEST",
    )
    value = seal_s8_input(s8_linear_input.model_copy(update={"runtime_commands": (command,), "content_sha256": "0"*64}))
    queue = m01_timeline.execute(value)
    assert queue.events[0].kind == StatefulEventKind.RUNTIME_COMMAND


def test_timeline_rejects_future_mark(s8_linear_input):
    mark = s8_linear_input.marks.marks[0].model_copy(update={
        "event_time": s8_linear_input.valuation_time + timedelta(seconds=1),
        "available_at": s8_linear_input.valuation_time + timedelta(seconds=1),
    })
    marks = s8_linear_input.marks.model_copy(update={"marks": (mark,)})
    value = seal_s8_input(s8_linear_input.model_copy(update={"marks": marks, "content_sha256": "0"*64}))
    with pytest.raises(TimelineIntegrityError):
        m01_timeline.execute(value)


def test_execution_state_replays_to_filled(s8_linear_input):
    queue = m01_timeline.execute(s8_linear_input)
    result = m02_execution_state.execute(s8_linear_input, queue)
    assert all(item.status == OrderStatus.FILLED for item in result.orders)
    assert sum((item.cumulative_filled_quantity for item in result.orders), Decimal("0")) == Decimal("10")


def test_execution_state_rejects_status_before_mismatch(s8_linear_input):
    queue = m01_timeline.execute(s8_linear_input)
    events = list(queue.events)
    idx = next(i for i,x in enumerate(events) if x.kind == StatefulEventKind.ORDER_EVENT)
    bad = events[idx].payload.model_copy(update={"status_before": OrderStatus.ACCEPTED})
    events[idx] = events[idx].model_copy(update={"payload": bad})
    tampered = OrderedEventQueue(events=tuple(events), content_sha256=queue.content_sha256)
    with pytest.raises(LedgerIntegrityError):
        m02_execution_state.execute(s8_linear_input, tampered)


def test_execution_state_rejects_fill_allocation_mismatch(s8_linear_input):
    queue = m01_timeline.execute(s8_linear_input)
    events = list(queue.events)
    idx = next(i for i,x in enumerate(events) if x.kind == StatefulEventKind.FILL_EVENT)
    fill = events[idx].payload
    alloc = fill.virtual_allocations[0].model_copy(update={"allocated_target_quantity": Decimal("999")})
    events[idx] = events[idx].model_copy(update={"payload": fill.model_copy(update={"virtual_allocations": (alloc,)})})
    with pytest.raises(LedgerIntegrityError):
        m02_execution_state.execute(s8_linear_input, OrderedEventQueue(events=tuple(events), content_sha256=queue.content_sha256))
