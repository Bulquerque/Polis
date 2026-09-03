from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class LinearMixedIntegerProblem:
    objective: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    integrality: np.ndarray
    a_lower: np.ndarray
    a_matrix: np.ndarray
    a_upper: np.ndarray
    time_limit_seconds: float
    mip_relative_gap: float


@dataclass(frozen=True)
class SolverResult:
    success: bool
    status: int
    message: str
    x: np.ndarray | None
    objective_value: float | None


class MixedIntegerSolverPort(Protocol):
    name: str
    version: str

    def solve(self, problem: LinearMixedIntegerProblem) -> SolverResult: ...
