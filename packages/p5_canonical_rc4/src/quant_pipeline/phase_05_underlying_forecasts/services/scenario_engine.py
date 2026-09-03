"""Deterministic block-bootstrap, copula path generation and scenario qualification."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import norm, rankdata, t

from ..errors import DataQualityError
from .identifiers import stable_id

_EPS = 1e-12


@dataclass(frozen=True, slots=True)
class ScenarioCandidate:
    method: str
    paths: np.ndarray
    score: float
    energy_score: float
    variogram_score: float


def univariate_path_bundle(
    values: np.ndarray,
    *,
    seed: int,
    count: int = 96,
    steps: int = 5,
    block_length: int | None = None,
) -> dict[str, Any]:
    array = _returns(values, minimum=24)
    if count < 24 or steps < 2:
        raise DataQualityError("scenario path bundle requires count>=24 and steps>=2")
    block = block_length or calibrated_block_length(array, steps)
    generator = np.random.default_rng(seed)
    methods = {
        "MOVING_BLOCK": _moving_block(array, generator, count // 3, steps, block),
        "STATIONARY_BLOCK": _stationary_block(array, generator, count // 3, steps, block),
        "REGIME_BLOCK": _regime_block(array, generator, count - 2 * (count // 3), steps, block),
    }
    candidates = [_candidate(name, paths, array) for name, paths in methods.items()]
    champion = min(candidates, key=lambda item: (item.score, item.method))
    nominal = champion.paths
    probabilities = np.full(len(nominal), 1.0 / len(nominal), dtype=float)
    stress = _univariate_stress_paths(array, steps)
    return {
        "champion_method": champion.method,
        "nominal_paths": nominal.tolist(),
        "nominal_probabilities": probabilities.tolist(),
        "stress_paths": stress,
        "candidate_scores": [_candidate_row(item) for item in candidates],
        "block_length": block,
        "effective_scenario_count": effective_count(probabilities),
        "tail_coverage": _tail_coverage(nominal[:, -1], array),
        "diversity_ratio": _diversity_ratio(nominal),
        "seed": seed,
    }


def joint_path_bundle(
    residuals: np.ndarray,
    centers: np.ndarray,
    *,
    seed: int,
    count: int = 96,
    steps: int = 5,
) -> dict[str, Any]:
    matrix = _matrix(residuals, minimum=30)
    center = np.asarray(centers, dtype=float)
    if center.shape != (matrix.shape[1],) or not np.all(np.isfinite(center)):
        raise DataQualityError("joint scenario centers must align with residual columns")
    train, holdout = _split_history(matrix)
    generator = np.random.default_rng(seed)
    candidate_paths = {
        "EMPIRICAL_COPULA": _empirical_copula_paths(train, generator, count, steps),
        "GAUSSIAN_COPULA": _gaussian_copula_paths(train, generator, count, steps),
        "T_COPULA": _t_copula_paths(train, generator, count, steps),
    }
    candidates = [_candidate(name, paths, holdout) for name, paths in candidate_paths.items()]
    champion = min(candidates, key=lambda item: (item.score, item.method))
    paths = champion.paths + center[None, None, :]
    probabilities = np.full(len(paths), 1.0 / len(paths), dtype=float)
    return {
        "champion_method": champion.method,
        "nominal_paths": paths.tolist(),
        "nominal_probabilities": probabilities.tolist(),
        "stress_paths": _joint_stress_paths(train, center, steps),
        "candidate_scores": [_candidate_row(item) for item in candidates],
        "effective_scenario_count": effective_count(probabilities),
        "tail_coverage": _tail_coverage(paths[:, -1, :].ravel(), (holdout + center).ravel()),
        "diversity_ratio": _diversity_ratio(paths),
        "seed": seed,
        "path_steps": steps,
    }


def validate_scenario_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    paths = np.asarray(bundle.get("nominal_paths", ()), dtype=float)
    probabilities = np.asarray(bundle.get("nominal_probabilities", ()), dtype=float)
    failures: list[str] = []
    if paths.ndim not in {2, 3} or len(paths) < 2 or not np.all(np.isfinite(paths)):
        failures.append("INVALID_NOMINAL_PATHS")
    if probabilities.shape != (len(paths),) or np.any(probabilities <= 0.0):
        failures.append("INVALID_NOMINAL_PROBABILITIES")
    elif abs(float(np.sum(probabilities)) - 1.0) > 1e-8:
        failures.append("INVALID_SCENARIO_MASS")
    stress = bundle.get("stress_paths", [])
    if any(item.get("probability") is not None for item in stress if isinstance(item, dict)):
        failures.append("STRESS_PROBABILITY_FORBIDDEN")
    effective = effective_count(probabilities) if len(probabilities) else 0.0
    if effective < min(8.0, max(2.0, len(probabilities) / 4.0)):
        failures.append("INSUFFICIENT_EFFECTIVE_SCENARIOS")
    diversity = _diversity_ratio(paths) if paths.size else 0.0
    if diversity < 0.10:
        failures.append("SCENARIO_COLLAPSE")
    return {
        "passed": not failures,
        "failures": failures,
        "nominal_scenario_count": int(len(paths)),
        "stress_scenario_count": len(stress),
        "probability_mass": float(np.sum(probabilities)) if len(probabilities) else 0.0,
        "effective_scenario_count": effective,
        "diversity_ratio": diversity,
        "tail_coverage": bundle.get("tail_coverage"),
        "champion_method": bundle.get("champion_method"),
    }


def calibrated_block_length(values: np.ndarray, steps: int) -> int:
    array = _returns(values, minimum=12)
    centered = array - np.mean(array)
    variance = max(float(np.dot(centered, centered)), _EPS)
    correlations = [float(np.dot(centered[:-lag], centered[lag:]) / variance) for lag in range(1, min(10, len(array) // 3))]
    persistence = sum(max(value, 0.0) for value in correlations)
    return int(np.clip(round(1.0 + 2.0 * persistence), 2, max(2, min(steps, 10))))


def effective_count(probabilities: np.ndarray) -> float:
    values = np.asarray(probabilities, dtype=float)
    total = float(np.sum(values))
    if total <= 0.0:
        return 0.0
    normalized = values / total
    return float(1.0 / np.sum(normalized**2))


def energy_score(paths: np.ndarray, observed: np.ndarray) -> float:
    samples = _terminal(paths)
    observations = _observations(observed, samples.shape[1])
    first = np.mean(np.linalg.norm(samples[:, None, :] - observations[None, :, :], axis=2))
    pairwise = np.mean(np.linalg.norm(samples[:, None, :] - samples[None, :, :], axis=2))
    return float(first - 0.5 * pairwise)


def variogram_score(paths: np.ndarray, observed: np.ndarray, power: float = 0.5) -> float:
    samples = _terminal(paths)
    observations = _observations(observed, samples.shape[1])
    if samples.shape[1] == 1:
        forecast = np.mean(np.abs(samples[:, 0])**power)
        truth = np.mean(np.abs(observations[:, 0])**power)
        return float((forecast - truth) ** 2)
    score = 0.0
    for left in range(samples.shape[1]):
        for right in range(left + 1, samples.shape[1]):
            forecast = np.mean(np.abs(samples[:, left] - samples[:, right])**power)
            truth = np.mean(np.abs(observations[:, left] - observations[:, right])**power)
            score += float((forecast - truth) ** 2)
    return score


def _candidate(method: str, paths: np.ndarray, observed: np.ndarray) -> ScenarioCandidate:
    energy = energy_score(paths, observed)
    variogram = variogram_score(paths, observed)
    return ScenarioCandidate(method, paths, energy + variogram, energy, variogram)


def _candidate_row(item: ScenarioCandidate) -> dict[str, Any]:
    return {
        "method": item.method,
        "qualification_score": item.score,
        "energy_score": item.energy_score,
        "variogram_score": item.variogram_score,
        "scenario_count": int(len(item.paths)),
    }


def _moving_block(values, generator, count, steps, block):
    paths = np.empty((count, steps), dtype=float)
    starts = generator.integers(0, len(values), size=(count, int(np.ceil(steps / block))))
    for row in range(count):
        sequence: list[float] = []
        for start in starts[row]:
            sequence.extend(values[(int(start) + offset) % len(values)] for offset in range(block))
        paths[row] = sequence[:steps]
    return paths


def _stationary_block(values, generator, count, steps, block):
    paths = np.empty((count, steps), dtype=float)
    restart = 1.0 / block
    for row in range(count):
        index = int(generator.integers(0, len(values)))
        for step in range(steps):
            paths[row, step] = values[index]
            index = int(generator.integers(0, len(values))) if generator.random() < restart else (index + 1) % len(values)
    return paths


def _regime_block(values, generator, count, steps, block):
    scale = np.asarray([np.std(values[max(0, index - 9):index + 1]) for index in range(len(values))])
    high = scale > np.median(scale)
    pools = {False: np.flatnonzero(~high), True: np.flatnonzero(high)}
    current = bool(high[-1])
    paths = np.empty((count, steps), dtype=float)
    for row in range(count):
        state = current
        for step in range(steps):
            pool = pools[state] if len(pools[state]) else np.arange(len(values))
            index = int(generator.choice(pool))
            paths[row, step] = values[index]
            if (step + 1) % block == 0 and generator.random() < 0.25:
                state = not state
    return paths


def _empirical_copula_paths(values, generator, count, steps):
    indexes = generator.integers(0, len(values), size=(count, steps))
    return values[indexes]


def _gaussian_copula_paths(values, generator, count, steps):
    uniforms, sorted_values = _copula_inputs(values)
    latent = norm.ppf(np.clip(uniforms, 1e-6, 1.0 - 1e-6))
    correlation = _nearest_correlation(np.corrcoef(latent, rowvar=False))
    draws = generator.multivariate_normal(np.zeros(values.shape[1]), correlation, size=(count, steps))
    return _inverse_empirical(norm.cdf(draws), sorted_values)


def _t_copula_paths(values, generator, count, steps, degrees: float = 6.0):
    uniforms, sorted_values = _copula_inputs(values)
    latent = t.ppf(np.clip(uniforms, 1e-6, 1.0 - 1e-6), df=degrees)
    correlation = _nearest_correlation(np.corrcoef(latent, rowvar=False))
    normals = generator.multivariate_normal(np.zeros(values.shape[1]), correlation, size=(count, steps))
    scales = np.sqrt(generator.chisquare(degrees, size=(count, steps, 1)) / degrees)
    return _inverse_empirical(t.cdf(normals / scales, df=degrees), sorted_values)


def _copula_inputs(values):
    uniforms = np.column_stack([rankdata(values[:, column], method="average") / (len(values) + 1.0) for column in range(values.shape[1])])
    return uniforms, np.sort(values, axis=0)


def _inverse_empirical(uniforms, sorted_values):
    output = np.empty_like(uniforms, dtype=float)
    grid = np.linspace(0.0, 1.0, len(sorted_values))
    for column in range(sorted_values.shape[1]):
        output[..., column] = np.interp(uniforms[..., column], grid, sorted_values[:, column])
    return output


def _nearest_correlation(matrix):
    value = np.asarray(matrix, dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh((value + value.T) / 2.0)
    repaired = (eigenvectors * np.maximum(eigenvalues, 1e-8)) @ eigenvectors.T
    diagonal = np.sqrt(np.maximum(np.diag(repaired), 1e-12))
    return (repaired / np.outer(diagonal, diagonal) + (repaired / np.outer(diagonal, diagonal)).T) / 2.0


def _univariate_stress_paths(values, steps):
    scale = max(float(np.std(values, ddof=1)), 1e-6)
    return [
        _stress("TAIL_AMPLIFICATION", np.full(steps, float(np.quantile(values, 0.01)) - scale)),
        _stress("VOLATILITY_SHOCK", np.asarray([(-1.0) ** index * 2.5 * scale for index in range(steps)])),
        _stress("REGIME_TRANSITION", np.linspace(float(np.median(values)), float(np.quantile(values, 0.02)), steps)),
    ]


def _joint_stress_paths(values, center, steps):
    scale = np.maximum(np.std(values, axis=0, ddof=1), 1e-6)
    lower = np.quantile(values, 0.01, axis=0) + center
    common = center - 3.0 * scale
    return [
        _stress("CROSS_ASSET_TAIL", np.repeat(lower[None, :], steps, axis=0)),
        _stress("CORRELATION_CRISIS", np.repeat(common[None, :], steps, axis=0)),
        _stress("VOLATILITY_AND_LIQUIDITY_SHOCK", np.vstack([center + ((-1.0) ** step) * 2.5 * scale for step in range(steps)])),
    ]


def _stress(name, path):
    array = np.asarray(path, dtype=float)
    return {"stress_id": stable_id("scenario-stress", name, array.tolist()), "stress_type": name, "path": array.tolist(), "probability": None}


def _tail_coverage(generated, observed):
    generated_values = np.asarray(generated, dtype=float).ravel()
    observed_values = np.asarray(observed, dtype=float).ravel()
    lower, upper = np.quantile(observed_values, [0.05, 0.95])
    return {
        "generated_lower_tail_share": float(np.mean(generated_values <= lower)),
        "generated_upper_tail_share": float(np.mean(generated_values >= upper)),
        "target_tail_share": 0.05,
    }


def _diversity_ratio(paths):
    array = np.asarray(paths, dtype=float)
    if len(array) < 2:
        return 0.0
    flattened = np.round(array.reshape(len(array), -1), 12)
    unique = np.unique(flattened, axis=0)
    return float(len(unique) / len(array))


def _terminal(paths):
    array = np.asarray(paths, dtype=float)
    if array.ndim == 2:
        return array[:, -1, None]
    if array.ndim == 3:
        return array[:, -1, :]
    raise DataQualityError("scenario paths must be two- or three-dimensional")


def _observations(values, width):
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array[:, None]
    if array.ndim != 2 or array.shape[1] != width or not np.all(np.isfinite(array)):
        raise DataQualityError("scenario scoring observations do not align")
    return array


def _split_history(values):
    cut = max(20, int(round(len(values) * 0.80)))
    cut = min(cut, len(values) - 8)
    return values[:cut], values[cut:]


def _returns(values, minimum):
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) < minimum or not np.all(np.isfinite(array)) or np.any(array <= -1.0):
        raise DataQualityError(f"scenario generator requires {minimum} finite returns above -1")
    return array

def _matrix(values, minimum):
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or len(array) < minimum or array.shape[1] < 2 or not np.all(np.isfinite(array)):
        raise DataQualityError("joint scenario generator requires a finite multivariate residual matrix")
    return array
