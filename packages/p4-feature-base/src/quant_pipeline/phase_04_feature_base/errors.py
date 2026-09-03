from __future__ import annotations

from enum import StrEnum
from typing import Any


class BoundaryErrorCode(StrEnum):
    INPUT_MISSING = "P4_S1_INPUT_MISSING"
    INPUT_NOT_MATERIALIZED = "P4_S1_INPUT_NOT_MATERIALIZED"
    SCHEMA_INVALID = "P4_S1_SCHEMA_INVALID"
    FORBIDDEN_FIELD = "P4_S1_FORBIDDEN_FIELD"
    PRIVATE_FIELD = "P4_S1_PRIVATE_FIELD"
    HASH_MISMATCH = "P4_S1_HASH_MISMATCH"
    MANIFEST_MISMATCH = "P4_S1_MANIFEST_MISMATCH"
    UNAUTHORIZED_PRODUCER = "P4_S1_UNAUTHORIZED_PRODUCER"
    PIPELINE_VERSION_MISMATCH = "P4_S1_PIPELINE_VERSION_MISMATCH"
    RUN_MISMATCH = "P4_S1_RUN_MISMATCH"
    CYCLE_MISMATCH = "P4_S1_CYCLE_MISMATCH"
    AS_OF_MISMATCH = "P4_S1_AS_OF_MISMATCH"
    UNIVERSE_MISMATCH = "P4_S1_UNIVERSE_MISMATCH"
    QUALITY_BLOCKED = "P4_S1_QUALITY_BLOCKED"
    HIDDEN_BUNDLE = "P4_S1_HIDDEN_BUNDLE"
    N_PLUS_1_BINDING_MISSING = "P4_S1_N_PLUS_1_BINDING_MISSING"
    N_PLUS_1_SAME_CYCLE = "P4_S1_N_PLUS_1_SAME_CYCLE"
    N_PLUS_1_NOT_PRIOR = "P4_S1_N_PLUS_1_NOT_PRIOR"
    TEMPORAL_INVALID = "P4_S1_TEMPORAL_INVALID"
    OUTPUT_INVALID = "P4_S1_OUTPUT_INVALID"


class BoundaryContractError(ValueError):
    """Deterministic P4.S1 contract failure with a stable code."""

    def __init__(
        self,
        code: BoundaryErrorCode,
        message: str,
        *,
        path: str = "$",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.path = path
        self.details = details or {}
        super().__init__(f"{code.value} at {path}: {message}")
