from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from tests.agents.a4.conftest import NOW, make_handoff
from quant_pipeline.phase_08_portfolio_control.foundation.enums import RuntimeControlMode
from quant_pipeline.phase_08_portfolio_control.foundation.errors import AuthorizationError, StateTransitionError
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution import m01_intents, m02_structure, m03_routing, m05_engine
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import RuntimeControlCommand
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.input_models import S7ToS8Handoff, S8InputBundle
from quant_pipeline.phase_08_portfolio_control.subphases.s08_stateful_engine.sealing import seal_s7_handoff, seal_s8_input


def _orders(stock_bundle, stock_market, context, venue_capabilities, policies):
    intents = m01_intents.execute(stock_bundle, context, policies.intent)
    structures = m02_structure.execute(intents, stock_bundle, venue_capabilities, policies.structure)
    return m03_routing.execute(
        intents, structures, stock_bundle, stock_market, venue_capabilities, context, policies.routing
    )


def _command(stock_bundle, *, command_id: str, sequence: int, run_id: str | None = None,
             cycle_id: str | None = None, source_hash: str | None = None):
    return RuntimeControlCommand(
        command_id=command_id,
        event_time=NOW,
        mode=RuntimeControlMode.HALT,
        reason_code="HARDENED_REGRESSION",
        run_id=run_id,
        cycle_id=cycle_id,
        source_state_hash=source_hash,
        valid_until=NOW + timedelta(minutes=5),
        command_sequence=sequence,
        feasibility_proven=True,
    )


def test_s7_rejects_foreign_execution_context(stock_bundle, context, policies):
    foreign = context.model_copy(update={"run_id": "foreign-run"})
    with pytest.raises(AuthorizationError, match="run/cycle"):
        m01_intents.execute(stock_bundle, foreign, policies.intent)


def test_s7_rejects_foreign_runtime_command(
    stock_bundle, stock_market, context, venue_capabilities, policies
):
    orders = _orders(stock_bundle, stock_market, context, venue_capabilities, policies)
    command = _command(
        stock_bundle, command_id="foreign", sequence=1,
        run_id="foreign-run", cycle_id=stock_bundle.cycle_id,
        source_hash=stock_bundle.content_sha256,
    )
    with pytest.raises(StateTransitionError, match="foreign runtime command run"):
        m05_engine.execute(orders, (), (command,), stock_bundle, context, policies.execution)


def test_s7_rejects_repeated_runtime_command_sequence(
    stock_bundle, stock_market, context, venue_capabilities, policies
):
    orders = _orders(stock_bundle, stock_market, context, venue_capabilities, policies)
    first = _command(
        stock_bundle, command_id="first", sequence=1,
        run_id=stock_bundle.run_id, cycle_id=stock_bundle.cycle_id,
        source_hash=stock_bundle.content_sha256,
    )
    second = _command(
        stock_bundle, command_id="second", sequence=1,
        run_id=stock_bundle.run_id, cycle_id=stock_bundle.cycle_id,
        source_hash=stock_bundle.content_sha256,
    )
    with pytest.raises(StateTransitionError, match="non-increasing|strictly increasing"):
        m05_engine.execute(orders, (), (first, second), stock_bundle, context, policies.execution)


def test_s7_to_s8_handoff_rejects_shifted_decision_time(stock_bundle, s7_linear_result):
    with pytest.raises(ValidationError, match="decision_time"):
        S7ToS8Handoff(
            handoff_id="shifted",
            producer_release="s7-1.0.0",
            run_id=stock_bundle.run_id,
            cycle_id=stock_bundle.cycle_id,
            decision_time=stock_bundle.decision_time + timedelta(seconds=1),
            authorization_bundle=stock_bundle,
            s7_result=s7_linear_result,
            content_sha256="0" * 64,
        )


def test_s8_rejects_foreign_runtime_command(s8_linear_input):
    auth = s8_linear_input.s7_handoff.authorization_bundle
    command = _command(
        auth, command_id="foreign-s8", sequence=1,
        run_id="foreign-run", cycle_id=s8_linear_input.cycle_id,
        source_hash=auth.content_sha256,
    )
    payload = s8_linear_input.model_dump(mode="python")
    payload.update({"runtime_commands": (command,), "content_sha256": "0" * 64})
    with pytest.raises(ValidationError, match="runtime command run mismatch"):
        S8InputBundle(**payload)
