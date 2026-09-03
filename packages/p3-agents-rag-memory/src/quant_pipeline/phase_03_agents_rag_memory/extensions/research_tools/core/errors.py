"""Typed configuration and contract failures for S32."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ResearchToolContractError(ValueError):
    def __init__(self, reason_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = dict(details)

    def as_dict(self) -> dict[str, object]:
        return {
            "reason_code": self.reason_code,
            "message": str(self),
            "details": self.details,
        }


def fail(reason_code: str, message: str, details: Mapping[str, Any] | None = None) -> ResearchToolContractError:
    return ResearchToolContractError(reason_code, message, **dict(details or {}))
