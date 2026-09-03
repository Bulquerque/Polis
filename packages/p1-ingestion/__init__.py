"""RC4.1 phase package with contract-gated orchestration entrypoints."""

from __future__ import annotations

class ContractValidationError(ValueError):
    """Raised when an input or output violates a V14.1 RC4.1 contract."""


def fail_fast(condition: bool, message: str) -> None:
    """Raise immediately when a contract condition fails."""
    if not condition:
        raise ContractValidationError(message)