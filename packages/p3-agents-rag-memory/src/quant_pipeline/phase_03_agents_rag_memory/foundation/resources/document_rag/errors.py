from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    CONTRACT = "CONTRACT"
    TEMPORAL = "TEMPORAL"
    LINEAGE = "LINEAGE"
    PROVIDER = "PROVIDER"
    PERSISTENCE = "PERSISTENCE"
    INVARIANT = "INVARIANT"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    category: ErrorCategory
    severity: str
    retryable: bool
    message: str
    redacted_context: dict[str, Any]


class P3S12Error(RuntimeError):
    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(f"{detail.code}: {detail.message}")
        self.detail = detail


class InputContractError(P3S12Error):
    pass


class TemporalViolationError(P3S12Error):
    pass


class ProviderFailureError(P3S12Error):
    pass


class PersistenceFailureError(P3S12Error):
    pass


class InvariantViolationError(P3S12Error):
    pass


def error(
    code: str,
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool = False,
    context: dict[str, Any] | None = None,
) -> ErrorDetail:
    return ErrorDetail(
        code=code,
        category=category,
        severity="ERROR",
        retryable=retryable,
        message=message,
        redacted_context=context or {},
    )
