"""Immutable numerical containers for P8.S4 risk-state artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.arrays import (
    ScenarioSet,
    StressScenarioSet,
)

from .errors import NumericalIntegrityError


def _readonly(value: np.ndarray, ndim: int) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype=np.float64)
    if array.ndim != ndim:
        raise NumericalIntegrityError(f"expected {ndim} dimensions, got {array.ndim}")
    if not np.all(np.isfinite(array)):
        raise NumericalIntegrityError("array contains non-finite values")
    array.setflags(write=False)
    return array


def load_stress_npz(path: Path) -> StressScenarioSet:
    with np.load(path, allow_pickle=False) as data:
        tags = tuple(tuple(str(x).split("|") if str(x) else ()) for x in data["tags"])
        return StressScenarioSet(
            values=data["values"],
            stress_ids=tuple(str(x) for x in data["stress_ids"]),
            factor_ids=tuple(str(x) for x in data["factor_ids"]),
            step_labels=tuple(str(x) for x in data["step_labels"]),
            severities=tuple(float(x) for x in data["severities"]),
            tags=tags,
        )


@dataclass(frozen=True, slots=True)
class ScenarioPnLCube:
    candidate_pnl: np.ndarray
    leg_pnl: np.ndarray
    stress_candidate_pnl: np.ndarray
    stress_leg_pnl: np.ndarray
    probabilities: np.ndarray
    scenario_ids: tuple[str, ...]
    stress_ids: tuple[str, ...]
    step_labels: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    leg_ids: tuple[str, ...]
    leg_candidate_ids: tuple[str, ...]
    pnl_semantics: str = "CUMULATIVE_FROM_DECISION"

    def __post_init__(self) -> None:
        candidate_pnl = _readonly(self.candidate_pnl, 3)
        leg_pnl = _readonly(self.leg_pnl, 3)
        stress_candidate_pnl = _readonly(self.stress_candidate_pnl, 3)
        stress_leg_pnl = _readonly(self.stress_leg_pnl, 3)
        probabilities = _readonly(self.probabilities, 1)
        scenarios, steps, candidates = candidate_pnl.shape
        stress_count, stress_steps, stress_candidates = stress_candidate_pnl.shape
        if leg_pnl.shape[:2] != (scenarios, steps):
            raise NumericalIntegrityError("leg and candidate scenario coordinates differ")
        if stress_leg_pnl.shape[:2] != (stress_count, stress_steps):
            raise NumericalIntegrityError("stress leg and candidate coordinates differ")
        if (stress_steps, stress_candidates) != (steps, candidates):
            raise NumericalIntegrityError("nominal and stress candidate coordinates differ")
        if probabilities.shape != (scenarios,):
            raise NumericalIntegrityError("probability length differs from scenarios")
        if len(self.scenario_ids) != scenarios or len(self.stress_ids) != stress_count:
            raise NumericalIntegrityError("scenario metadata length mismatch")
        if len(self.step_labels) != steps or len(self.candidate_ids) != candidates:
            raise NumericalIntegrityError("candidate coordinate registry mismatch")
        if len(self.leg_ids) != leg_pnl.shape[2] or len(self.leg_candidate_ids) != leg_pnl.shape[2]:
            raise NumericalIntegrityError("leg coordinate registry mismatch")
        if stress_leg_pnl.shape[2] != len(self.leg_ids):
            raise NumericalIntegrityError("nominal and stress leg count differs")
        if self.pnl_semantics not in {"CUMULATIVE_FROM_DECISION", "INCREMENTAL_STEP"}:
            raise NumericalIntegrityError(f"unsupported PnL semantics: {self.pnl_semantics}")
        if not np.isclose(probabilities.sum(), 1.0, atol=1e-10, rtol=0.0):
            raise NumericalIntegrityError("probabilities do not sum to one")
        object.__setattr__(self, "candidate_pnl", candidate_pnl)
        object.__setattr__(self, "leg_pnl", leg_pnl)
        object.__setattr__(self, "stress_candidate_pnl", stress_candidate_pnl)
        object.__setattr__(self, "stress_leg_pnl", stress_leg_pnl)
        object.__setattr__(self, "probabilities", probabilities)

    def content_sha256(self) -> str:
        digest = hashlib.sha256()
        for array in (
            self.candidate_pnl, self.leg_pnl, self.stress_candidate_pnl,
            self.stress_leg_pnl, self.probabilities,
        ):
            digest.update(array.tobytes(order="C"))
        digest.update(json.dumps({
            "scenario_ids": self.scenario_ids,
            "stress_ids": self.stress_ids,
            "step_labels": self.step_labels,
            "candidate_ids": self.candidate_ids,
            "leg_ids": self.leg_ids,
            "leg_candidate_ids": self.leg_candidate_ids,
            "pnl_semantics": self.pnl_semantics,
        }, sort_keys=True, separators=(",", ":")).encode())
        return digest.hexdigest()

    def save_npz(self, path: Path) -> None:
        np.savez_compressed(
            path,
            candidate_pnl=self.candidate_pnl,
            leg_pnl=self.leg_pnl,
            stress_candidate_pnl=self.stress_candidate_pnl,
            stress_leg_pnl=self.stress_leg_pnl,
            probabilities=self.probabilities,
            scenario_ids=np.asarray(self.scenario_ids),
            stress_ids=np.asarray(self.stress_ids),
            step_labels=np.asarray(self.step_labels),
            candidate_ids=np.asarray(self.candidate_ids),
            leg_ids=np.asarray(self.leg_ids),
            leg_candidate_ids=np.asarray(self.leg_candidate_ids),
            pnl_semantics=np.asarray(self.pnl_semantics),
        )

    @classmethod
    def load_npz(cls, path: Path) -> "ScenarioPnLCube":
        with np.load(path, allow_pickle=False) as data:
            return cls(
                candidate_pnl=data["candidate_pnl"],
                leg_pnl=data["leg_pnl"],
                stress_candidate_pnl=data["stress_candidate_pnl"],
                stress_leg_pnl=data["stress_leg_pnl"],
                probabilities=data["probabilities"],
                scenario_ids=tuple(str(x) for x in data["scenario_ids"]),
                stress_ids=tuple(str(x) for x in data["stress_ids"]),
                step_labels=tuple(str(x) for x in data["step_labels"]),
                candidate_ids=tuple(str(x) for x in data["candidate_ids"]),
                leg_ids=tuple(str(x) for x in data["leg_ids"]),
                leg_candidate_ids=tuple(str(x) for x in data["leg_candidate_ids"]),
                pnl_semantics=(
                    str(data["pnl_semantics"].item())
                    if "pnl_semantics" in data.files
                    else "CUMULATIVE_FROM_DECISION"
                ),
            )


@dataclass(frozen=True, slots=True)
class DependenceArrays:
    covariance: np.ndarray
    correlation: np.ndarray
    lower_tail_dependence: np.ndarray
    upper_tail_dependence: np.ndarray
    tail_asymmetry: np.ndarray
    candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        arrays = tuple(_readonly(x, 2) for x in (
            self.covariance, self.correlation, self.lower_tail_dependence,
            self.upper_tail_dependence, self.tail_asymmetry,
        ))
        size = len(self.candidate_ids)
        if any(array.shape != (size, size) for array in arrays):
            raise NumericalIntegrityError("dependence matrices have inconsistent shape")
        object.__setattr__(self, "covariance", arrays[0])
        object.__setattr__(self, "correlation", arrays[1])
        object.__setattr__(self, "lower_tail_dependence", arrays[2])
        object.__setattr__(self, "upper_tail_dependence", arrays[3])
        object.__setattr__(self, "tail_asymmetry", arrays[4])

    def content_sha256(self) -> str:
        digest = hashlib.sha256()
        for array in (
            self.covariance, self.correlation, self.lower_tail_dependence,
            self.upper_tail_dependence, self.tail_asymmetry,
        ):
            digest.update(array.tobytes(order="C"))
        digest.update(json.dumps({"candidate_ids": self.candidate_ids}, separators=(",", ":")).encode())
        return digest.hexdigest()

    def save_npz(self, path: Path) -> None:
        np.savez_compressed(
            path,
            covariance=self.covariance,
            correlation=self.correlation,
            lower_tail_dependence=self.lower_tail_dependence,
            upper_tail_dependence=self.upper_tail_dependence,
            tail_asymmetry=self.tail_asymmetry,
            candidate_ids=np.asarray(self.candidate_ids),
        )


@dataclass(frozen=True, slots=True)
class GreekPathArrays:
    candidate_greeks: np.ndarray
    greek_coverage: np.ndarray
    current_portfolio_greeks: np.ndarray
    mean_max_drawdown: np.ndarray
    tail_max_drawdown: np.ndarray
    worst_step_loss: np.ndarray
    candidate_ids: tuple[str, ...]
    greek_names: tuple[str, ...]

    def __post_init__(self) -> None:
        candidate_greeks = _readonly(self.candidate_greeks, 2)
        greek_coverage = _readonly(self.greek_coverage, 2)
        current_portfolio_greeks = _readonly(self.current_portfolio_greeks, 1)
        mean_max_drawdown = _readonly(self.mean_max_drawdown, 1)
        tail_max_drawdown = _readonly(self.tail_max_drawdown, 1)
        worst_step_loss = _readonly(self.worst_step_loss, 1)
        candidate_count = len(self.candidate_ids)
        greek_count = len(self.greek_names)
        if candidate_greeks.shape != (candidate_count, greek_count):
            raise NumericalIntegrityError("candidate Greek matrix shape mismatch")
        if greek_coverage.shape != (candidate_count, greek_count):
            raise NumericalIntegrityError("Greek coverage matrix shape mismatch")
        if np.any((greek_coverage < 0.0) | (greek_coverage > 1.0)):
            raise NumericalIntegrityError("Greek coverage must be between zero and one")
        if current_portfolio_greeks.shape != (greek_count,):
            raise NumericalIntegrityError("portfolio Greek vector shape mismatch")
        if any(x.shape != (candidate_count,) for x in (mean_max_drawdown, tail_max_drawdown, worst_step_loss)):
            raise NumericalIntegrityError("path metric coordinate mismatch")
        object.__setattr__(self, "candidate_greeks", candidate_greeks)
        object.__setattr__(self, "greek_coverage", greek_coverage)
        object.__setattr__(self, "current_portfolio_greeks", current_portfolio_greeks)
        object.__setattr__(self, "mean_max_drawdown", mean_max_drawdown)
        object.__setattr__(self, "tail_max_drawdown", tail_max_drawdown)
        object.__setattr__(self, "worst_step_loss", worst_step_loss)

    def content_sha256(self) -> str:
        digest = hashlib.sha256()
        for array in (
            self.candidate_greeks, self.greek_coverage, self.current_portfolio_greeks,
            self.mean_max_drawdown, self.tail_max_drawdown, self.worst_step_loss,
        ):
            digest.update(array.tobytes(order="C"))
        digest.update(json.dumps({
            "candidate_ids": self.candidate_ids,
            "greek_names": self.greek_names,
        }, sort_keys=True, separators=(",", ":")).encode())
        return digest.hexdigest()

    def save_npz(self, path: Path) -> None:
        np.savez_compressed(
            path,
            candidate_greeks=self.candidate_greeks,
            greek_coverage=self.greek_coverage,
            current_portfolio_greeks=self.current_portfolio_greeks,
            mean_max_drawdown=self.mean_max_drawdown,
            tail_max_drawdown=self.tail_max_drawdown,
            worst_step_loss=self.worst_step_loss,
            candidate_ids=np.asarray(self.candidate_ids),
            greek_names=np.asarray(self.greek_names),
        )
