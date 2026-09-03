from __future__ import annotations

from enum import StrEnum
from typing import Mapping, Any


class ExecutionProfile(StrEnum):
    """Runtime profile controlling whether local/reference adapters are allowed."""

    TEST = "TEST"
    REPLAY = "REPLAY"
    LIVE = "LIVE"


def resolve_execution_profile(
    config: Mapping[str, Any] | None,
) -> ExecutionProfile:
    raw = str((config or {}).get("execution_profile", "TEST")).upper()
    try:
        return ExecutionProfile(raw)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported execution_profile {raw!r}; expected TEST, REPLAY or LIVE"
        ) from exc
