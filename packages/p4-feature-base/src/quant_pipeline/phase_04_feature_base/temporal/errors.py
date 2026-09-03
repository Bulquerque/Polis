from __future__ import annotations

from enum import StrEnum
from typing import Any


class TemporalErrorCode(StrEnum):
    INPUT_MISSING = "P4_S2_INPUT_MISSING"
    INPUT_INVALID = "P4_S2_INPUT_INVALID"
    BOUNDARY_REFERENCE_MISMATCH = "P4_S2_BOUNDARY_REFERENCE_MISMATCH"
    SCHEMA_INVALID = "P4_S2_SCHEMA_INVALID"
    TEMPORAL_VALUE_MISSING = "P4_S2_TEMPORAL_VALUE_MISSING"
    TEMPORAL_VALUE_INVALID = "P4_S2_TEMPORAL_VALUE_INVALID"
    TIMEZONE_MISSING = "P4_S2_TIMEZONE_MISSING"
    TIMEZONE_UNKNOWN = "P4_S2_TIMEZONE_UNKNOWN"
    DST_AMBIGUOUS = "P4_S2_DST_AMBIGUOUS"
    DST_NONEXISTENT = "P4_S2_DST_NONEXISTENT"
    FUTURE_AVAILABILITY = "P4_S2_FUTURE_AVAILABILITY"
    ENTITY_UNRESOLVED = "P4_S2_ENTITY_UNRESOLVED"
    CORPORATE_ACTION_ORDER_INVALID = "P4_S2_CORPORATE_ACTION_ORDER_INVALID"
    REVISION_TIE = "P4_S2_REVISION_TIE"
    CANONICAL_DUPLICATE = "P4_S2_CANONICAL_DUPLICATE"
    NON_FINITE_VALUE = "P4_S2_NON_FINITE_VALUE"
    OUTPUT_INVALID = "P4_S2_OUTPUT_INVALID"


class TemporalContractError(ValueError):
    """Deterministic P4.S2 failure with a stable error code."""

    def __init__(
        self,
        code: TemporalErrorCode,
        message: str,
        *,
        path: str = "$",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.details = details or {}
        super().__init__(f"{code.value} at {path}: {message}")
