from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..domain.problem import LinearOptimizationProblem
from ..models.enums import SolverStatus


@dataclass(frozen=True)
class RawSolverResult:
    status: SolverStatus
    x: np.ndarray | None
    objective_value: float | None
    message: str
    iterations: int | None
    solver_name: str
    solver_version: str


class PortfolioSolverPort(Protocol):
    def solve(self, problem: LinearOptimizationProblem) -> RawSolverResult: ...


class DiscreteSolverPort(Protocol):
    def solve_discrete(self, problem: LinearOptimizationProblem, increments: np.ndarray) -> RawSolverResult: ...
