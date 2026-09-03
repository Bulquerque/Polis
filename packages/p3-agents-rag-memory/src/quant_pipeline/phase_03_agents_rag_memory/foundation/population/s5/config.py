"""Explicit configuration loading at the package boundary."""
from __future__ import annotations
from pathlib import Path
from typing import TypeVar
import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

def load_yaml_model(path: Path, model_type: type[T]) -> T:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model_type.model_validate(raw, strict=False)

def load_prompt(path: Path) -> str:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"empty prompt: {path}")
    return content
