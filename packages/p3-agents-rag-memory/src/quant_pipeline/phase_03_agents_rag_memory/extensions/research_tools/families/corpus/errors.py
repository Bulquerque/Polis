from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    CONTRACT = "CONTRACT"
    CONFIGURATION = "CONFIGURATION"
    TEMPORAL = "TEMPORAL"
    DATA = "DATA"
    PROVIDER = "PROVIDER"
    INVARIANT = "INVARIANT"


@dataclass(frozen=True, slots=True)
class CorpusErrorDetail:
    code: str
    category: ErrorCategory
    message: str
    context: dict[str, object]


class CorpusToolError(RuntimeError):
    def __init__(self, detail: CorpusErrorDetail) -> None:
        super().__init__(f"{detail.code}: {detail.message}")
        self.detail = detail


def error(
    code: str,
    category: ErrorCategory,
    message: str,
    *,
    context: dict[str, object] | None = None,
) -> CorpusErrorDetail:
    return CorpusErrorDetail(
        code=code,
        category=category,
        message=message,
        context=context or {},
    )
