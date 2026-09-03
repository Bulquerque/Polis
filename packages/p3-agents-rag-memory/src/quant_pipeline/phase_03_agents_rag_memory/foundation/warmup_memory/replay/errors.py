from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class S11Issue:
    code: str
    message: str
    path: str = "root"
    details: dict[str, Any] | None = None


class WarmupReplayStateError(RuntimeError):
    """Base fail-closed error for P3.S11."""

    def __init__(self, issues: list[S11Issue] | tuple[S11Issue, ...]) -> None:
        normalized = tuple(issues) or (
            S11Issue(
                code="P3_S11_UNKNOWN_FAILURE",
                message="P3.S11 failed without a declared issue.",
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


class WarmupReplayError(WarmupReplayStateError):
    """P3.S11.M01 failed without publishing partial outputs."""


class BootstrapLeakageError(WarmupReplayStateError):
    """P3.S11.M02 detected leakage, authority drift or invalid lineage."""


class CycleStateLoadError(WarmupReplayStateError):
    """P3.S11.M03 could not select and materialize exactly one state source."""


class CheckpointStoreError(WarmupReplayStateError):
    """Checkpoint persistence or verification failed."""
