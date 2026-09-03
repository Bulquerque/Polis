from __future__ import annotations

import signal
import time

import pytest

from quant_pipeline.phase_09.errors import ExecutionTimeoutError
from quant_pipeline.phase_09.subphases.s03_backtest_tournament.m03_backtest_runner import (
    SignalExecutionController,
)


def test_signal_execution_controller_interrupts_or_fails_closed() -> None:
    controller = SignalExecutionController()
    started = time.perf_counter()
    called = False

    def operation() -> None:
        nonlocal called
        called = True
        time.sleep(0.2)

    with pytest.raises(ExecutionTimeoutError):
        controller.run(operation, timeout_seconds=0.01)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.15
    if not hasattr(signal, "setitimer"):
        assert called is False
