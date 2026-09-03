from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import importlib.util
import numpy as np

@dataclass(frozen=True)
class EncoderResult:
    config_id: str
    shared: np.ndarray
    private: dict[str, np.ndarray]
    reconstructed: np.ndarray
    state: dict[str, Any]
    search_records: list[dict[str, Any]]

def torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None

def train_encoder(*, inner_train: np.ndarray, inner_train_observed: np.ndarray,
                  inner_validation: np.ndarray, inner_validation_observed: np.ndarray,
                  final_train: np.ndarray, final_train_observed: np.ndarray,
                  transform: np.ndarray, transform_observed: np.ndarray,
                  modalities: dict[str, tuple[int, ...]], configs: tuple[Any, ...], max_epochs: int,
                  patience: int, learning_rate: float, weight_decay: float, huber_delta: float,
                  random_state: int) -> EncoderResult:
    if not torch_available():
        raise RuntimeError("PyTorch backend is unavailable")
    from .torch_encoder import train_select_refit
    return train_select_refit(inner_train=inner_train, inner_train_observed=inner_train_observed,
        inner_validation=inner_validation, inner_validation_observed=inner_validation_observed,
        final_train=final_train, final_train_observed=final_train_observed, transform=transform,
        transform_observed=transform_observed, modalities=modalities, configs=configs,
        max_epochs=max_epochs, patience=patience, learning_rate=learning_rate,
        weight_decay=weight_decay, huber_delta=huber_delta, random_state=random_state)
