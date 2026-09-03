from __future__ import annotations
from typing import Any
import numpy as np
import torch
from torch import nn
from .encoder_backend import EncoderResult

class ShallowSharedPrivateAE(nn.Module):
    def __init__(self, input_dim: int, shared_dim: int, modalities: dict[str, tuple[int, ...]]) -> None:
        super().__init__()
        self.modalities = modalities
        self.shared = nn.Sequential(nn.Linear(input_dim, shared_dim), nn.GELU())
        self.private = nn.ModuleDict({name: nn.Sequential(nn.Linear(len(indices), 1), nn.GELU()) for name, indices in modalities.items()})
        self.decoder = nn.Linear(shared_dim + len(modalities), input_dim)

    def encode(self, value: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        shared = self.shared(value)
        private = {name: module(value[:, list(self.modalities[name])]) for name, module in self.private.items()}
        return shared, private

    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:
        shared, private = self.encode(value)
        joined = torch.cat([shared] + [private[name] for name in sorted(private)], dim=1)
        return self.decoder(joined), shared, private

def _masked_loss(prediction: torch.Tensor, target: torch.Tensor, observed: torch.Tensor, delta: float) -> torch.Tensor:
    raw = nn.functional.huber_loss(prediction, target, reduction="none", delta=delta)
    weights = observed.to(raw.dtype)
    return (raw * weights).sum() / weights.sum().clamp_min(1.0)

def _corrupt(value: torch.Tensor, modalities: dict[str, tuple[int, ...]], corruption: float,
             modality_dropout: float, generator: torch.Generator) -> torch.Tensor:
    keep = torch.rand(value.shape, generator=generator, device=value.device) >= corruption
    output = value * keep
    for indices in modalities.values():
        if torch.rand((), generator=generator).item() < modality_dropout:
            output[:, list(indices)] = 0.0
    return output

def _new_model(input_dim: int, ratio: float, modalities: dict[str, tuple[int, ...]], seed: int) -> ShallowSharedPrivateAE:
    torch.manual_seed(seed)
    return ShallowSharedPrivateAE(input_dim, max(1, round(input_dim * ratio)), modalities)

def _fit_with_validation(train: torch.Tensor, observed: torch.Tensor, validation: torch.Tensor,
                         validation_observed: torch.Tensor, modalities: dict[str, tuple[int, ...]],
                         config: Any, max_epochs: int, patience: int, learning_rate: float,
                         weight_decay: float, delta: float, seed: int) -> tuple[dict[str, torch.Tensor], dict[str, Any]]:
    model = _new_model(train.shape[1], config.bottleneck_ratio, modalities, seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    best_state: dict[str, torch.Tensor] | None = None
    best_loss, best_epoch, stale = float("inf"), 0, 0
    for epoch in range(max_epochs):
        generator = torch.Generator().manual_seed(seed + epoch)
        model.train(); optimizer.zero_grad()
        reconstructed = model(_corrupt(train, modalities, config.corruption_rate, config.modality_dropout, generator))[0]
        loss = _masked_loss(reconstructed, train, observed, delta)
        loss.backward(); optimizer.step(); model.eval()
        with torch.no_grad():
            value = _masked_loss(model(validation)[0], validation, validation_observed, delta).item()
        if value + 1e-10 < best_loss:
            best_loss, best_epoch, stale = value, epoch + 1, 0
            best_state = {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}
        else:
            stale += 1
        if stale >= patience:
            break
    assert best_state is not None
    return best_state, {"config_id": config.config_id, "validation_loss": best_loss, "best_epoch": best_epoch}

def _refit(train: torch.Tensor, observed: torch.Tensor, modalities: dict[str, tuple[int, ...]], config: Any,
           epochs: int, learning_rate: float, weight_decay: float, delta: float, seed: int) -> ShallowSharedPrivateAE:
    model = _new_model(train.shape[1], config.bottleneck_ratio, modalities, seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    for epoch in range(max(1, epochs)):
        generator = torch.Generator().manual_seed(seed + epoch)
        model.train(); optimizer.zero_grad()
        reconstructed = model(_corrupt(train, modalities, config.corruption_rate, config.modality_dropout, generator))[0]
        loss = _masked_loss(reconstructed, train, observed, delta)
        loss.backward(); optimizer.step()
    return model

def train_select_refit(*, inner_train: np.ndarray, inner_train_observed: np.ndarray,
                       inner_validation: np.ndarray, inner_validation_observed: np.ndarray,
                       final_train: np.ndarray, final_train_observed: np.ndarray,
                       transform: np.ndarray, transform_observed: np.ndarray,
                       modalities: dict[str, tuple[int, ...]], configs: tuple[Any, ...], max_epochs: int,
                       patience: int, learning_rate: float, weight_decay: float, huber_delta: float,
                       random_state: int) -> EncoderResult:
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    tensors = [torch.tensor(value, dtype=torch.float32) for value in (inner_train, inner_validation, final_train, transform)]
    masks = [torch.tensor(value, dtype=torch.bool) for value in (inner_train_observed, inner_validation_observed, final_train_observed, transform_observed)]
    candidates = []
    for index, config in enumerate(configs):
        _, record = _fit_with_validation(tensors[0], masks[0], tensors[1], masks[1], modalities, config,
            max_epochs, patience, learning_rate, weight_decay, huber_delta, random_state + index * 1000)
        candidates.append((record["validation_loss"], config, record))
    candidates.sort(key=lambda item: (item[0], item[1].config_id))
    _, config, selected = candidates[0]
    model = _refit(tensors[2], masks[2], modalities, config, selected["best_epoch"], learning_rate,
        weight_decay, huber_delta, random_state + 9000)
    model.eval()
    with torch.no_grad(): reconstructed, shared, private = model(tensors[3])
    state = {name: tensor.detach().cpu().numpy().tolist() for name, tensor in model.state_dict().items()}
    search = [item[2] | {"selected": item[1].config_id == config.config_id} for item in candidates]
    return EncoderResult(config.config_id, shared.numpy(), {k: v.numpy() for k, v in private.items()},
        reconstructed.numpy(), {"weights": state, "selected": selected}, search)
