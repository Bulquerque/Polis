"""Shared deterministic resource budget for P6 solvers."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .solver_common import SolverData
from ..foundation.configuration import Phase6RunConfiguration


@dataclass
class SolverBudget:
    deadline: float | None
    node_limit: int
    estimated_memory_mb: float
    memory_limit_mb: int
    nodes: int = 0

    @classmethod
    def for_problem(cls, data: SolverData, configuration: Phase6RunConfiguration) -> "SolverBudget":
        seconds = configuration.budgets.max_solver_seconds
        cells = len(data.basis) * max(1, len(data.y))
        estimated = (cells * 8 * 8 + len(data.basis) * 2048) / (1024 * 1024)
        return cls(
            deadline=None if seconds <= 0 else monotonic() + seconds,
            node_limit=configuration.budgets.max_solver_nodes,
            estimated_memory_mb=estimated,
            memory_limit_mb=configuration.budgets.max_memory_mb,
        )

    @property
    def memory_ok(self) -> bool:
        return self.estimated_memory_mb <= self.memory_limit_mb

    @property
    def expired(self) -> bool:
        return self.deadline is not None and monotonic() >= self.deadline

    def consume(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("budget consumption cannot be negative")
        if not self.memory_ok or self.expired or self.nodes + count > self.node_limit:
            return False
        self.nodes += count
        return True

    @property
    def exhausted(self) -> bool:
        return not self.memory_ok or self.expired or self.nodes >= self.node_limit

    def diagnostics(self) -> tuple[str, ...]:
        values = []
        if not self.memory_ok:
            values.append("SOLVER_MEMORY_BUDGET_EXCEEDED")
        if self.expired:
            values.append("SOLVER_TIME_BUDGET_EXCEEDED")
        if self.nodes >= self.node_limit:
            values.append("SOLVER_NODE_BUDGET_EXHAUSTED")
        return tuple(values)
