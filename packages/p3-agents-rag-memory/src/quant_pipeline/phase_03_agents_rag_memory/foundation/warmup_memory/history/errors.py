from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str = "root"
    details: dict[str, Any] | None = None


class WarmupHistoryValidationError(RuntimeError):
    """Raised when P3.S9 fails closed without producing a partial artifact."""

    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]) -> None:
        normalized = tuple(issues)
        if not normalized:
            normalized = (
                ValidationIssue(
                    code="P3_S9_M01_UNKNOWN_VALIDATION_FAILURE",
                    message="Warm-up history validation failed without a declared issue.",
                ),
            )
        self.issues = normalized
        super().__init__("; ".join(f"{issue.code}: {issue.message}" for issue in normalized))

    def to_dict(self) -> dict[str, object]:
        return {
            "error_type": self.__class__.__name__,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "path": issue.path,
                    "details": issue.details or {},
                }
                for issue in self.issues
            ],
        }
