from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class S14Issue:
    code: str
    message: str
    path: str = "root"
    details: dict[str, Any] | None = None


class MemoryFoundationError(RuntimeError):
    """Base fail-closed error for P3.S14."""

    def __init__(self, issues: list[S14Issue] | tuple[S14Issue, ...]) -> None:
        normalized = tuple(issues) or (
            S14Issue(code="P3_S14_UNKNOWN_FAILURE", message="P3.S14 failed without a declared issue."),
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


class MemoryPolicyError(MemoryFoundationError):
    """P3.S14.M01 could not compile a safe, fully resolved policy."""


class MemoryIndexError(MemoryFoundationError):
    """P3.S14.M02 could not build a safe deterministic index manifest."""


class MemoryIndexStoreError(MemoryFoundationError):
    """A memory-index storage adapter failed."""
