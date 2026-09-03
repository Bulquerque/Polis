from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..runtime_shared.s21_errors import S21DependencyError, S21InputError
from ..runtime_shared.s21_hashing import canonical_json

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_model(
    inputs: Mapping[str, object],
    key: str,
    model_type: type[ModelT],
    *,
    module_id: str,
) -> ModelT:
    if key not in inputs:
        raise S21InputError(
            code="INPUT_MISSING",
            message=f"required input is missing: {key}",
            module_id=module_id,
        )
    value = inputs[key]
    if isinstance(value, model_type):
        return value
    try:
        return model_type.model_validate_json(canonical_json(value))
    except ValidationError as exc:
        raise S21InputError(
            code="INPUT_INVALID",
            message=f"input failed validation: {key}",
            module_id=module_id,
            details={"errors": exc.errors(include_input=False)},
        ) from exc


def serialize_outputs(outputs: Mapping[str, object]) -> dict[str, object]:
    serialized: dict[str, object] = {}
    for key, value in outputs.items():
        if isinstance(value, BaseModel):
            serialized[key] = value.model_dump(mode="json")
        else:
            serialized[key] = value
    return serialized


def run_sync(coro: Awaitable[dict[str, object]], *, module_id: str) -> dict[str, object]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return serialize_outputs(asyncio.run(coro))
    raise S21DependencyError(
        code="ASYNC_ENTRYPOINT_REQUIRED",
        message="run_module_async must be used inside an active event loop",
        module_id=module_id,
    )
