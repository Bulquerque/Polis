"""Explicit YAML/JSON loaders for strict P3.S7 models."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
import yaml

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_yaml_model(path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")), strict=False)


def load_json_model(path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate(json.loads(path.read_text(encoding="utf-8")), strict=False)
