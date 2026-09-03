from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    CONTRACT = "CONTRACT"
    TEMPORAL = "TEMPORAL"
    PROVIDER = "PROVIDER"
    SECURITY = "SECURITY"
    POLICY = "POLICY"
    INVARIANT = "INVARIANT"
    AUDIT = "AUDIT"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    category: ErrorCategory
    message: str
    context: dict[str, Any]


class P3S16Error(RuntimeError):
    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(f"{detail.code}: {detail.message}")
        self.detail = detail


class ContractError(P3S16Error): pass
class TemporalError(P3S16Error): pass
class ProviderError(P3S16Error): pass
class SecurityError(P3S16Error): pass
class PolicyError(P3S16Error): pass
class InvariantError(P3S16Error): pass
class AuditError(P3S16Error): pass


def error(code: str, category: ErrorCategory, message: str, **context: Any) -> ErrorDetail:
    return ErrorDetail(code=code, category=category, message=message, context=dict(context))
