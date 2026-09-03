from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SchedulingIssue:
    code: str
    message: str
    path: str = "root"
    details: dict[str, Any] | None = None


class WarmupSchedulingError(RuntimeError):
    """Base fail-closed error for P3.S10."""

    def __init__(self, issues: list[SchedulingIssue] | tuple[SchedulingIssue, ...]) -> None:
        normalized = tuple(issues) or (
            SchedulingIssue(
                code="P3_S10_UNKNOWN_FAILURE",
                message="Warm-up scheduling failed without a declared issue.",
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


class WarmupScheduleBuildError(WarmupSchedulingError):
    """P3.S10.M01 failed without producing a partial schedule."""


class WarmupCheckpointPlanError(WarmupSchedulingError):
    """P3.S10.M02 failed without producing a partial checkpoint plan."""
