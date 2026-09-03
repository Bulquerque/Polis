"""Deterministic threshold and Gaussian-HMM regime candidates."""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.special import logsumexp

_EPS = 1e-12


def infer_regime(array: np.ndarray) -> dict[str, Any]:
    baseline = _threshold_regime(array)
    challenger = _gaussian_hmm(array)
    selected = challenger if challenger["bic"] < baseline["bic"] and challenger["stable"] else baseline
    return {
        "regime_labels": selected["regime_labels"],
        "current_regime": selected["current_regime"],
        "probabilities": selected["predicted_probabilities"],
        "filtered_probabilities": selected["filtered_probabilities"],
        "smoothed_probabilities": selected["smoothed_probabilities"],
        "predicted_probabilities": selected["predicted_probabilities"],
        "transition_matrix": selected["transition_matrix"],
        "expected_duration": selected["expected_duration"],
        "selected_method": selected["method"],
        "candidate_diagnostics": [baseline, challenger],
        "stability_status": "STABLE" if selected["stable"] else "UNSTABLE",
    }


def _threshold_regime(array: np.ndarray) -> dict[str, Any]:
    rolling = np.asarray([np.std(array[max(0, index - 9):index + 1], ddof=0) for index in range(len(array))])
    threshold = float(np.median(rolling))
    states = (rolling > threshold).astype(int)
    transitions, durations = _transition_statistics(states)
    current = int(states[-1])
    probabilities = {"LOW_VOL": float(transitions[current, 0]), "HIGH_VOL": float(transitions[current, 1])}
    variance = np.asarray([max(np.var(array[states == state]), 1e-8) for state in (0, 1)])
    likelihood = float(np.sum(np.log(np.maximum(np.where(states == 0, 1.0 / np.sqrt(variance[0]), 1.0 / np.sqrt(variance[1])), _EPS))))
    return {
        "method": "ROLLING_VOLATILITY_MARKOV_COUNTS",
        "regime_labels": ("LOW_VOL", "HIGH_VOL"),
        "current_regime": "HIGH_VOL" if current else "LOW_VOL",
        "filtered_probabilities": probabilities,
        "smoothed_probabilities": probabilities,
        "predicted_probabilities": probabilities,
        "transition_matrix": transitions.tolist(),
        "expected_duration": durations,
        "bic": float(-2.0 * likelihood + 4.0 * np.log(len(array))),
        "stable": all(value >= 2.0 for value in durations.values()),
        "state_threshold": threshold,
    }


def _gaussian_hmm(array: np.ndarray) -> dict[str, Any]:
    observations = array[:, None]
    means = np.quantile(array, [0.25, 0.75])
    variances = np.full(2, max(float(np.var(array)), 1e-6))
    transition = np.asarray([[0.95, 0.05], [0.05, 0.95]], dtype=float)
    initial = np.asarray([0.5, 0.5], dtype=float)
    previous = -np.inf
    gamma = np.full((len(array), 2), 0.5, dtype=float)
    for _ in range(60):
        log_emission = np.column_stack([
            -0.5 * (np.log(2.0 * np.pi * variances[state]) + (array - means[state]) ** 2 / variances[state])
            for state in range(2)
        ])
        gamma, xi, likelihood = _forward_backward(log_emission, transition, initial)
        weights = np.maximum(gamma.sum(axis=0), _EPS)
        means = (gamma * observations).sum(axis=0) / weights
        variances = np.maximum((gamma * (observations - means) ** 2).sum(axis=0) / weights, 1e-8)
        transition = np.maximum(xi.sum(axis=0), _EPS)
        transition /= transition.sum(axis=1, keepdims=True)
        initial = gamma[0]
        if abs(likelihood - previous) < 1e-8:
            previous = likelihood
            break
        previous = likelihood
    order = np.argsort(variances)
    gamma = gamma[:, order]
    transition = transition[np.ix_(order, order)]
    labels = ("LOW_VOL", "HIGH_VOL")
    filtered = {labels[index]: float(gamma[-1, index]) for index in range(2)}
    predicted_array = gamma[-1] @ transition
    predicted = {labels[index]: float(predicted_array[index]) for index in range(2)}
    expected = {labels[index]: float(1.0 / max(1.0 - transition[index, index], 1e-6)) for index in range(2)}
    return {
        "method": "GAUSSIAN_HMM_EM",
        "regime_labels": labels,
        "current_regime": labels[int(np.argmax(predicted_array))],
        "filtered_probabilities": filtered,
        "smoothed_probabilities": filtered,
        "predicted_probabilities": predicted,
        "transition_matrix": transition.tolist(),
        "expected_duration": expected,
        "bic": float(-2.0 * previous + 7.0 * np.log(len(array))),
        "stable": bool(np.all(np.isfinite(transition)) and all(value >= 2.0 for value in expected.values())),
        "state_means": means[order].tolist(),
        "state_variances": variances[order].tolist(),
    }


def _forward_backward(log_emission: np.ndarray, transition: np.ndarray, initial: np.ndarray):
    count = len(log_emission)
    log_transition = np.log(np.maximum(transition, _EPS))
    alpha = np.empty_like(log_emission)
    alpha[0] = np.log(np.maximum(initial, _EPS)) + log_emission[0]
    for index in range(1, count):
        alpha[index] = log_emission[index] + logsumexp(alpha[index - 1][:, None] + log_transition, axis=0)
    likelihood = float(logsumexp(alpha[-1]))
    beta = np.zeros_like(log_emission)
    for index in range(count - 2, -1, -1):
        beta[index] = logsumexp(log_transition + log_emission[index + 1] + beta[index + 1], axis=1)
    gamma = np.exp(alpha + beta - likelihood)
    xi = np.empty((count - 1, 2, 2), dtype=float)
    for index in range(count - 1):
        xi[index] = np.exp(alpha[index][:, None] + log_transition + log_emission[index + 1] + beta[index + 1] - likelihood)
    return gamma, xi, likelihood


def _transition_statistics(states: np.ndarray):
    transitions = np.ones((2, 2), dtype=float)
    durations: dict[int, list[int]] = {0: [], 1: []}
    state, length = int(states[0]), 1
    for left, right in zip(states[:-1], states[1:], strict=True):
        transitions[left, right] += 1.0
        if int(right) == state:
            length += 1
        else:
            durations[state].append(length)
            state, length = int(right), 1
    durations[state].append(length)
    transitions /= transitions.sum(axis=1, keepdims=True)
    return transitions, {
        "LOW_VOL": float(np.mean(durations[0])) if durations[0] else 0.0,
        "HIGH_VOL": float(np.mean(durations[1])) if durations[1] else 0.0,
    }
