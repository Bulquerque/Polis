from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode


def parse_aware_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise BoundaryContractError(BoundaryErrorCode.TEMPORAL_INVALID, "blank datetime", path=field_name)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise BoundaryContractError(
                BoundaryErrorCode.TEMPORAL_INVALID, "invalid ISO-8601 datetime", path=field_name
            ) from exc
    else:
        raise BoundaryContractError(
            BoundaryErrorCode.TEMPORAL_INVALID, "datetime must be a string or datetime", path=field_name
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BoundaryContractError(
            BoundaryErrorCode.TEMPORAL_INVALID, "datetime must be timezone-aware", path=field_name
        )
    return parsed.astimezone(UTC)


def utc_z(value: datetime) -> str:
    return parse_aware_datetime(value, "datetime").isoformat().replace("+00:00", "Z")
