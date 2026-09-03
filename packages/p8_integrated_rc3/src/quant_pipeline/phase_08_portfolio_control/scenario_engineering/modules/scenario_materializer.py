"""P8.S3.M02 contextual scenario materialization engine."""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

from ..arrays import ScenarioSet
from ..contracts import (
    BeliefRecord, EmpiricalPayload, HistoricalScenarioPanel, MixtureComponent,
    MixturePayload, ParametricPayload, PathPayload, QuantilePayload, ScenarioPolicy,
)
from ..errors import ContractIntegrityError, ProbabilityIntegrityError, TemporalIntegrityError
from ..random_stream import RandomStream

MODULE_ID = "P8.S3.M02"


def _draw_uniforms(stream: RandomStream, count: int, dimension: int, method: str) -> np.ndarray:
    if method == "SOBOL":
        return stream.sobol_uniforms(dimension, count)
    return stream.generator().random((count, dimension))


def _draw_component(component: MixtureComponent, count: int, rng: np.random.Generator) -> np.ndarray:
    mean = np.asarray(component.mean, dtype=np.float64)
    covariance = np.asarray(component.covariance, dtype=np.float64)
    normal = rng.multivariate_normal(mean, covariance, size=count, check_valid="raise")
    if component.family == "NORMAL":
        return normal
    scale = np.sqrt(component.degrees_freedom / rng.chisquare(component.degrees_freedom, size=count))
    return mean + (normal - mean) * scale[:, None]


def _materialize_payload(belief: BeliefRecord, policy: ScenarioPolicy) -> np.ndarray:
    payload = belief.payload
    count = policy.scenario_count
    stream = RandomStream(policy.seed_entropy, f"{belief.belief_state_id}:nominal")
    rng = stream.generator()
    if isinstance(payload, ParametricPayload):
        component = MixtureComponent(
            weight=1.0, family=payload.family, mean=payload.mean,
            covariance=payload.covariance, degrees_freedom=payload.degrees_freedom,
        )
        return _draw_component(component, count, rng)[:, None, :]
    if isinstance(payload, MixturePayload):
        weights = np.asarray([c.weight for c in payload.components], dtype=np.float64)
        assignments = rng.choice(len(payload.components), size=count, p=weights)
        result = np.empty((count, len(belief.factor_ids)), dtype=np.float64)
        for index, component in enumerate(payload.components):
            mask = np.flatnonzero(assignments == index)
            if len(mask):
                result[mask] = _draw_component(component, len(mask), rng)
        return result[:, None, :]
    if isinstance(payload, QuantilePayload):
        uniforms = _draw_uniforms(stream, count, len(belief.factor_ids), policy.sampling_method)
        if payload.gaussian_copula_correlation is not None:
            correlation = np.asarray(payload.gaussian_copula_correlation, dtype=np.float64)
            z = norm.ppf(np.clip(uniforms, policy.quantile_epsilon, 1.0-policy.quantile_epsilon))
            transformed = z @ np.linalg.cholesky(correlation + np.eye(len(correlation))*1e-12).T
            uniforms = norm.cdf(transformed)
        levels = np.asarray(payload.levels, dtype=np.float64)
        values = np.asarray(payload.values, dtype=np.float64)
        result = np.column_stack([
            np.interp(uniforms[:, factor], levels, values[:, factor])
            for factor in range(values.shape[1])
        ])
        return result[:, None, :]
    if isinstance(payload, EmpiricalPayload):
        samples = np.asarray(payload.samples, dtype=np.float64)
        probabilities = _probabilities(payload.probabilities, len(samples))
        selected = rng.choice(len(samples), size=count, replace=True, p=probabilities)
        return samples[selected, None, :]
    if isinstance(payload, PathPayload):
        paths = np.asarray(payload.paths, dtype=np.float64)
        probabilities = _probabilities(payload.probabilities, len(paths))
        selected = rng.choice(len(paths), size=count, replace=True, p=probabilities)
        return paths[selected]
    raise ContractIntegrityError("unsupported distribution payload")


def _probabilities(raw: tuple[float, ...] | None, count: int) -> np.ndarray:
    if raw is None:
        return np.full(count, 1.0/count, dtype=np.float64)
    values = np.asarray(raw, dtype=np.float64)
    if not np.isclose(values.sum(), 1.0, atol=1e-10, rtol=0.0):
        raise ProbabilityIntegrityError("source probabilities must sum to one")
    return values


def _historical_values(panel: HistoricalScenarioPanel, belief: BeliefRecord) -> np.ndarray:
    if panel.factor_ids != belief.factor_ids:
        raise ContractIntegrityError("historical factor registry differs from belief")
    if any(timestamp > panel.decision_time for timestamp in panel.sample_available_at):
        raise TemporalIntegrityError("historical panel contains future-available samples")
    samples = np.asarray(panel.samples, dtype=np.float64)
    if samples.ndim != 2 or samples.shape[1] != len(belief.factor_ids):
        raise ContractIntegrityError("historical samples shape mismatch")
    return samples[:, None, :]


def materialize_scenarios(
    belief: BeliefRecord,
    policy: ScenarioPolicy,
    historical: HistoricalScenarioPanel | None = None,
) -> ScenarioSet:
    generated = _materialize_payload(belief, policy)
    values = generated
    origins = ["P5_MODEL"] * len(generated)
    probabilities = np.full(len(generated), 1.0/len(generated), dtype=np.float64)
    if historical is not None and policy.historical_weight > 0.0:
        history = _historical_values(historical, belief)
        if history.shape[1:] != generated.shape[1:]:
            raise ContractIntegrityError("historical paths do not share generated time grid")
        historical_probabilities = _probabilities(historical.probabilities, len(history))
        probabilities *= 1.0 - policy.historical_weight
        historical_probabilities *= policy.historical_weight
        values = np.concatenate([generated, history], axis=0)
        probabilities = np.concatenate([probabilities, historical_probabilities])
        origins.extend(["P2_FILTERED_HISTORICAL"] * len(history))
    probabilities = probabilities / probabilities.sum()
    step_labels = belief.payload.step_labels if isinstance(belief.payload, PathPayload) else ("EVALUATION_HORIZON",)
    scenario_ids = tuple(f"SCN-{index:06d}" for index in range(len(values)))
    return ScenarioSet(
        values=values,
        probabilities=probabilities,
        scenario_ids=scenario_ids,
        factor_ids=belief.factor_ids,
        step_labels=step_labels,
        origins=tuple(origins),
    )
