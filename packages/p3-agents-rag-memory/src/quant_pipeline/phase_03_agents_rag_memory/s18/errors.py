from __future__ import annotations


class S18Error(RuntimeError):
    """Base class for P3.S18 fail-closed errors."""

    code = "P3_S18_ERROR"


class S18InputError(S18Error):
    code = "P3_S18_INPUT_INVALID"


class S18TemporalViolationError(S18Error):
    code = "P3_S18_TEMPORAL_VIOLATION"


class S18LineageError(S18Error):
    code = "P3_S18_LINEAGE_INVALID"


class S18HashMismatchError(S18Error):
    code = "P3_S18_HASH_MISMATCH"


class S18DuplicateConflictError(S18Error):
    code = "P3_S18_DUPLICATE_CONFLICT"


class S18ForbiddenFieldError(S18Error):
    code = "P3_S18_FORBIDDEN_FIELD"


class S18OutputError(S18Error):
    code = "P3_S18_OUTPUT_INVALID"
