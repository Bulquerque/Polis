from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VariableLayout:
    horizon_count: int
    candidate_count: int
    scenario_count: int
    ordinal_count: int
    q: slice
    trade_abs: slice
    position_abs: slice
    zeta: int
    xi: slice
    inversion: slice
    total_size: int

    @classmethod
    def create(cls, horizons: int, candidates: int, scenarios: int, ordinal: int) -> "VariableLayout":
        block = horizons * candidates
        q = slice(0, block)
        trade_abs = slice(block, 2 * block)
        position_abs = slice(2 * block, 3 * block)
        zeta = 3 * block
        xi = slice(zeta + 1, zeta + 1 + scenarios)
        inversion = slice(xi.stop, xi.stop + ordinal)
        return cls(horizons, candidates, scenarios, ordinal, q, trade_abs, position_abs, zeta, xi, inversion, inversion.stop)

    def q_index(self, horizon: int, candidate: int) -> int:
        return self.q.start + horizon * self.candidate_count + candidate

    def trade_index(self, horizon: int, candidate: int) -> int:
        return self.trade_abs.start + horizon * self.candidate_count + candidate

    def position_index(self, horizon: int, candidate: int) -> int:
        return self.position_abs.start + horizon * self.candidate_count + candidate


@dataclass(frozen=True)
class LinearOptimizationProblem:
    c: np.ndarray
    a_ub: np.ndarray
    b_ub: np.ndarray
    a_eq: np.ndarray
    b_eq: np.ndarray
    bounds: tuple[tuple[float | None, float | None], ...]
    layout: VariableLayout
    constraint_names: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    horizon_ids: tuple[str, ...]
    input_hash: str
