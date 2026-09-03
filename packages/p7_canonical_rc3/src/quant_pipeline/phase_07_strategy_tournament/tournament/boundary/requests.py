from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Mapping

from pydantic import Field

from .base import TimeAwareModel


class ModuleExecutionConfig(TimeAwareModel):
    _time_fields = ("execution_time",)

    execution_time: datetime
    strict_hash_validation: bool = True
    emit_debug_events: bool = True
    numerical_tolerance: float = Field(default=1e-10, ge=0, allow_inf_nan=False)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ModuleExecutionConfig":
        return cls.model_validate_json(json.dumps(dict(value), allow_nan=False, sort_keys=True))
