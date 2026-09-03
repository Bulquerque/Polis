from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar('ModelT', bound=BaseModel)


def parse_json_artifact(model_type: type[ModelT], payload: str | bytes) -> ModelT:
    """Parse standards-compliant JSON into a strict immutable domain model.

    JSON has arrays and RFC 3339 strings, while the domain uses tuples and timezone-aware
    datetimes. Coercion is allowed only at this explicit boundary; model validators and
    ``extra='forbid'`` still run before the model is returned.
    """
    return model_type.model_validate_json(payload, strict=False)
