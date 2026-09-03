"""Immutable numerical containers used by scenario modules."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .errors import NumericalIntegrityError, ProbabilityIntegrityError


def _readonly_float_array(value: np.ndarray, ndim: int) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype=np.float64)
    if array.ndim != ndim:
        raise NumericalIntegrityError(f"expected {ndim} dimensions, got {array.ndim}")
    if not np.all(np.isfinite(array)):
        raise NumericalIntegrityError("array contains non-finite values")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, slots=True)
class ScenarioSet:
    values: np.ndarray
    probabilities: np.ndarray
    scenario_ids: tuple[str, ...]
    factor_ids: tuple[str, ...]
    step_labels: tuple[str, ...]
    origins: tuple[str, ...]

    def __post_init__(self) -> None:
        values = _readonly_float_array(self.values, 3)
        probabilities = _readonly_float_array(self.probabilities, 1)
        count, steps, factors = values.shape
        if probabilities.shape != (count,):
            raise ProbabilityIntegrityError("probability vector length mismatch")
        if len(self.scenario_ids) != count or len(self.origins) != count:
            raise NumericalIntegrityError("scenario metadata length mismatch")
        if len(self.factor_ids) != factors or len(self.step_labels) != steps:
            raise NumericalIntegrityError("coordinate registry length mismatch")
        if np.any(probabilities < 0.0):
            raise ProbabilityIntegrityError("negative scenario probability")
        total = float(probabilities.sum())
        if not np.isclose(total, 1.0, atol=1e-10, rtol=0.0):
            raise ProbabilityIntegrityError(f"probabilities sum to {total}, expected 1")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "probabilities", probabilities)

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.values.shape

    def flattened(self) -> np.ndarray:
        return self.values.reshape(self.values.shape[0], -1)

    def content_sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.values.tobytes(order="C"))
        digest.update(self.probabilities.tobytes(order="C"))
        metadata = {
            "scenario_ids": self.scenario_ids,
            "factor_ids": self.factor_ids,
            "step_labels": self.step_labels,
            "origins": self.origins,
        }
        digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
        return digest.hexdigest()

    def save_npz(self, path: Path) -> None:
        np.savez_compressed(
            path,
            values=self.values,
            probabilities=self.probabilities,
            scenario_ids=np.asarray(self.scenario_ids),
            factor_ids=np.asarray(self.factor_ids),
            step_labels=np.asarray(self.step_labels),
            origins=np.asarray(self.origins),
        )

    @classmethod
    def load_npz(cls, path: Path) -> "ScenarioSet":
        with np.load(path, allow_pickle=False) as data:
            return cls(
                values=data["values"],
                probabilities=data["probabilities"],
                scenario_ids=tuple(str(x) for x in data["scenario_ids"]),
                factor_ids=tuple(str(x) for x in data["factor_ids"]),
                step_labels=tuple(str(x) for x in data["step_labels"]),
                origins=tuple(str(x) for x in data["origins"]),
            )


@dataclass(frozen=True, slots=True)
class StressScenarioSet:
    values: np.ndarray
    stress_ids: tuple[str, ...]
    factor_ids: tuple[str, ...]
    step_labels: tuple[str, ...]
    severities: tuple[float, ...]
    tags: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        values = _readonly_float_array(self.values, 3)
        count, steps, factors = values.shape
        if len(self.stress_ids) != count or len(self.severities) != count or len(self.tags) != count:
            raise NumericalIntegrityError("stress metadata length mismatch")
        if len(self.factor_ids) != factors or len(self.step_labels) != steps:
            raise NumericalIntegrityError("stress coordinate registry mismatch")
        object.__setattr__(self, "values", values)

    def content_sha256(self) -> str:
        digest = hashlib.sha256(self.values.tobytes(order="C"))
        digest.update(json.dumps({
            "stress_ids": self.stress_ids,
            "factor_ids": self.factor_ids,
            "step_labels": self.step_labels,
            "severities": self.severities,
            "tags": self.tags,
        }, sort_keys=True, separators=(",", ":")).encode())
        return digest.hexdigest()
