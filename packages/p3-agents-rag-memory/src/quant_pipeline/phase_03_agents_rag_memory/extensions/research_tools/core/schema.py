"""JSON Schema 2020-12 generation and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any, TypeVar

from jsonschema import Draft202012Validator
from pydantic import BaseModel

from .hashing import content_hash

ModelT = TypeVar("ModelT", bound=BaseModel)
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def schema_for(model: type[ModelT], schema_id: str) -> dict[str, Any]:
    schema = deepcopy(model.model_json_schema(mode="validation"))
    schema["$schema"] = DIALECT
    schema["$id"] = schema_id
    Draft202012Validator.check_schema(schema)
    return schema


def validate_schema_bundle(entries: Iterable[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for entry in entries:
        schema_id = str(entry["schema_id"])
        if schema_id in indexed:
            raise ValueError(f"duplicate schema_id: {schema_id}")
        indexed[schema_id] = entry
    return indexed


def schema_hash(schema: Mapping[str, object]) -> str:
    return content_hash(schema)
