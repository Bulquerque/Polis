"""Load the four versioned S7 policies without custom YAML tags."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from .boundary.config import S7Config
from .boundary.s8_config import S8Config


def _load_mapping(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must contain a mapping: {path}")
    return data


def load_s7_config(policy_root: str | Path, runtime: Mapping[str, object]) -> S7Config:
    root = Path(policy_root)
    payload = {
        "runtime": dict(runtime),
        "similarity": _load_mapping(root / "similarity_policy.yaml"),
        "diversity": _load_mapping(root / "diversity_policy.yaml"),
        "safety": _load_mapping(root / "safety_policy.yaml"),
        "abstention": _load_mapping(root / "abstention_policy.yaml"),
        "forbidden_fields": ("future_return", "realized_return", "realized_pnl", "future_pnl", "target_outcome", "realized_outcome"),
    }
    return S7Config.model_validate(payload)



def load_s8_config(policy_root: str | Path, runtime: Mapping[str, object]) -> S8Config:
    root = Path(policy_root)
    payload = {
        "runtime": dict(runtime),
        "ranking": _load_mapping(root / "ranking_policy.yaml"),
        "thesis": _load_mapping(root / "thesis_policy.yaml"),
        "publication": _load_mapping(root / "publication_policy.yaml"),
        "forbidden_fields": (
            "future_return", "realized_return", "realized_pnl", "future_pnl",
            "target_outcome", "realized_outcome", "portfolio_weight", "position_size",
            "execution_price",
        ),
    }
    return S8Config.model_validate(payload)
