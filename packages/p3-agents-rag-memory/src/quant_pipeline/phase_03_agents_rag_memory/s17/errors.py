from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ErrorContext:
    module_id: str
    code: str
    message: str
    details: Mapping[str, object]


class S17Error(RuntimeError):
    """Base fail-closed exception for P3.S17."""

    def __init__(
        self,
        *,
        module_id: str,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.context = ErrorContext(
            module_id=module_id,
            code=code,
            message=message,
            details=details or {},
        )
        super().__init__(f"{module_id}:{code}: {message}")


class InputContractError(S17Error):
    """Input does not satisfy the declared contract."""


class TemporalViolationError(S17Error):
    """A record violates point-in-time semantics."""


class ForbiddenFieldError(S17Error):
    """A forbidden economic-authority field was detected."""


class ResolutionContractError(S17Error):
    """Underlying or proposition resolution contract failed."""


class ProviderAdapterError(S17Error):
    """An optional external identifier provider failed materially."""
