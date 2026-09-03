"""Strict immutable contract primitives shared by P8 subphases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


AwareDatetime = Annotated[datetime, AfterValidator(_ensure_aware_utc)]
NonEmptyStr = Annotated[str, StringConstraints(strict=True, min_length=1)]
CurrencyCode = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{3}$")]
SHA256Str = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]


class StrictModel(BaseModel):
    """Base model for every public/internal DTO crossing a module boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        revalidate_instances="always",
        allow_inf_nan=False,
        str_strip_whitespace=False,
        ser_json_temporal="iso8601",
    )
