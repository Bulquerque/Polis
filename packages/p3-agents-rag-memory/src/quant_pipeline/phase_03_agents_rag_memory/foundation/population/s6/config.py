"""Explicit YAML/JSON boundary loaders for strict Pydantic models."""
from __future__ import annotations
from pathlib import Path
from typing import TypeVar
import json
import yaml
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)

def load_yaml_model(path: Path, model_type: type[ModelT]) -> ModelT:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model_type.model_validate(raw, strict=False)

def load_json_model(path: Path, model_type: type[ModelT]) -> ModelT:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return model_type.model_validate(raw, strict=False)
