from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..runtime_shared.s23_errors import S23ContractError
from ..runtime_shared.s23_hashing import canonical_json

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_model(
    inputs: Mapping[str, object],
    name: str,
    model: type[ModelT],
    *,
    module_id: str,
) -> ModelT:
    if name not in inputs:
        raise S23ContractError(code="MISSING_REQUIRED_INPUT", message=name, module_id=module_id)
    try:
        value = inputs[name]
        if isinstance(value, model):
            return value
        return model.model_validate_json(canonical_json(value))
    except ValidationError as exc:
        raise S23ContractError(code="INPUT_SCHEMA_INVALID", message=f"{name}:{exc}", module_id=module_id) from exc
