from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

try:
    from quant_pipeline.phase_03_agents_rag_memory.contracts.base import (  # type: ignore
        ContractModel as MacroToolModel,
        canonical_json,
        content_hash,
    )
except ModuleNotFoundError:
    class MacroToolModel(BaseModel):
        """Standalone fallback only; the integrated P3 ContractModel remains authoritative."""

        model_config = ConfigDict(
            strict=True,
            extra="forbid",
            frozen=True,
            validate_default=True,
            str_strip_whitespace=True,
        )

    def _default(value: object) -> object:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("datetime must be timezone-aware")
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        raise TypeError(type(value).__name__)

    def canonical_json(value: object) -> str:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=_default,
        )

    def content_hash(value: object) -> str:
        return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

JsonObject = dict[str, Any]


def validate_json(model: type[BaseModel], value: object) -> BaseModel:
    """Validate JSON-shaped data while preserving strict Python-side contracts."""
    return model.model_validate_json(canonical_json(value))
