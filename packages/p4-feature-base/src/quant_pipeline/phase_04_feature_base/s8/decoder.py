"""Portable decoders for the representations emitted by P4.S8."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


class DecoderError(ValueError):
    """Raised when a representation cannot be reconstructed safely."""


def _array(value: Any, *, name: str, ndim: int | None = None) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if ndim is not None and result.ndim != ndim:
        raise DecoderError(f"{name} must have ndim={ndim}, got {result.ndim}")
    if not np.isfinite(result).all():
        raise DecoderError(f"{name} contains non-finite values")
    return result


def decode_linear(scores: Sequence[float] | np.ndarray, fit_state: Mapping[str, Any]) -> np.ndarray:
    """Decode one or more PCA/Sparse-PCA scores using a fit-state record."""

    components = _array(fit_state.get("components"), name="components", ndim=2)
    mean = _array(fit_state.get("mean"), name="mean", ndim=1)
    values = _array(scores, name="scores")
    if values.ndim == 1:
        values = values.reshape(1, -1)
    if values.ndim != 2 or values.shape[1] != components.shape[0]:
        raise DecoderError(
            "scores shape is incompatible with components: "
            f"scores={values.shape}, components={components.shape}"
        )
    if mean.shape[0] != components.shape[1]:
        raise DecoderError(
            "mean length is incompatible with components: "
            f"mean={mean.shape}, components={components.shape}"
        )
    return values @ components + mean


def decode_encoder(
    shared_latent: Sequence[float] | np.ndarray,
    private_latents: Mapping[str, Sequence[float] | np.ndarray],
    fit_state: Mapping[str, Any],
) -> np.ndarray:
    """Decode the portable linear decoder stored by the optional AE path."""

    model_state = fit_state.get("model_state", fit_state)
    weights = model_state.get("weights", model_state)
    decoder_weight = _array(weights.get("decoder.weight"), name="decoder.weight", ndim=2)
    decoder_bias = _array(weights.get("decoder.bias"), name="decoder.bias", ndim=1)
    shared = _array(shared_latent, name="shared_latent")
    if shared.ndim == 1:
        shared = shared.reshape(1, -1)
    if shared.ndim != 2:
        raise DecoderError("shared_latent must be one- or two-dimensional")
    names = sorted(private_latents)
    private = []
    for name in names:
        value = _array(private_latents[name], name=f"private_latents[{name}]")
        if value.ndim == 1:
            value = value.reshape(1, -1)
        if value.ndim != 2 or value.shape[0] != shared.shape[0]:
            raise DecoderError(f"private latent shape is invalid for modality {name}")
        private.append(value)
    joined = np.concatenate([shared, *private], axis=1) if private else shared
    if joined.shape[1] != decoder_weight.shape[1] or decoder_bias.shape[0] != decoder_weight.shape[0]:
        raise DecoderError(
            "latent shape is incompatible with decoder weights: "
            f"joined={joined.shape}, weight={decoder_weight.shape}, bias={decoder_bias.shape}"
        )
    return joined @ decoder_weight.T + decoder_bias


def decode_record(record: Mapping[str, Any], fit_state: Mapping[str, Any]) -> np.ndarray:
    """Decode a factor or embedding record according to its representation type."""

    kind = str(record.get("representation_type", "")).upper()
    if kind in {"PCA", "SPARSE_PCA"}:
        return decode_linear(record.get("component_values"), fit_state)
    if kind == "ENCODER" or "shared_latent" in record:
        return decode_encoder(record.get("shared_latent"), record.get("private_latents", {}), fit_state)
    raise DecoderError(f"unsupported representation type: {kind or 'UNKNOWN'}")


def observed_rmse(decoded: np.ndarray, expected: np.ndarray, observed: np.ndarray | None = None) -> float:
    """Return RMSE over observed cells, rejecting shape mismatches."""

    actual = _array(decoded, name="decoded")
    target = _array(expected, name="expected")
    if actual.shape != target.shape:
        raise DecoderError(f"decoded and expected shapes differ: {actual.shape} != {target.shape}")
    mask = np.ones(actual.shape, dtype=bool) if observed is None else np.asarray(observed, dtype=bool)
    if mask.shape != actual.shape:
        raise DecoderError(f"observed mask shape differs: {mask.shape} != {actual.shape}")
    errors = (actual - target)[mask]
    return float(np.sqrt(np.mean(errors**2))) if errors.size else 0.0
