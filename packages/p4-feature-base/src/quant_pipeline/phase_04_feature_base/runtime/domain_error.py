from __future__ import annotations

from typing import Any


class P4DomainError(RuntimeError):
    """Stable diagnostic error shared across P4 subphases."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        module_id: str | None = None,
        severity: str = "ERROR",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.module_id = module_id
        self.severity = severity
        self.retryable = retryable
        self.details = details or {}
        prefix = f"{module_id} " if module_id else ""
        super().__init__(f"{prefix}{code}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "module_id": self.module_id,
            "severity": self.severity,
            "retryable": self.retryable,
            "details": dict(self.details),
        }
