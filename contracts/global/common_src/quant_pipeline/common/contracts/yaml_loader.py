from __future__ import annotations
from pathlib import Path
import yaml


def load_yaml(path: str | Path) -> dict:
    # Load a YAML file and fail fast if the top-level object is not a mapping.
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing YAML file: {p}")
    with p.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {p}")
    return data
