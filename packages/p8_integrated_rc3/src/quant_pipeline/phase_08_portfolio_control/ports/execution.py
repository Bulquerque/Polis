from __future__ import annotations

from typing import Protocol, Sequence

from ..subphases.s07_execution.models import ExecutionCommand, MarketEvent, PlannedOrder


class MarketEventPort(Protocol):
    def events(self) -> Sequence[MarketEvent]: ...


class BrokerExecutionPort(Protocol):
    def submit(self, order: PlannedOrder) -> str: ...
    def cancel(self, broker_order_id: str) -> None: ...


class ExecutionCommandPort(Protocol):
    def commands(self) -> Sequence[ExecutionCommand]: ...
