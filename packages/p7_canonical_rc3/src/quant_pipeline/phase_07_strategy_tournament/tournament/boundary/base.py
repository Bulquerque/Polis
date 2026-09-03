from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from ..domain.time import require_timezone_aware


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TimeAwareModel(StrictModel):
    _time_fields: ClassVar[tuple[str, ...]] = ()

    @field_validator("*", mode="after")
    @classmethod
    def validate_time_fields(cls, value: Any, info: Any) -> Any:
        if info.field_name in cls._time_fields and isinstance(value, datetime):
            return require_timezone_aware(value, info.field_name)
        return value
