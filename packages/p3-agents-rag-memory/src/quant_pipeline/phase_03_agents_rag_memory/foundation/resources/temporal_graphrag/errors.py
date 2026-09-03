from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    CONTRACT = "CONTRACT"
    TEMPORAL = "TEMPORAL"
    INVARIANT = "INVARIANT"
    PROVIDER = "PROVIDER"
    PERSISTENCE = "PERSISTENCE"
    SECURITY = "SECURITY"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    category: ErrorCategory
    message: str
    context: dict[str, Any] = field(default_factory=dict)


def error(code: str, category: ErrorCategory, message: str, *, context: dict[str, Any] | None = None) -> ErrorDetail:
    return ErrorDetail(code=code, category=category, message=message, context=context or {})


class P3S13Error(RuntimeError):
    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(f"{detail.code}: {detail.message}")
        self.detail = detail


class ContractError(P3S13Error):
    pass


class TemporalViolationError(P3S13Error):
    pass


class InvariantViolationError(P3S13Error):
    pass


class ProviderFailureError(P3S13Error):
    pass


class PersistenceFailureError(P3S13Error):
    pass
