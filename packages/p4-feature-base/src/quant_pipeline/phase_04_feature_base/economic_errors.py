from __future__ import annotations
from typing import Any
from .runtime.domain_error import P4DomainError

class P4S4Error(P4DomainError):
    """Base fail-fast economic-pipeline error with a stable code."""
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, module_id="P4.S4-S6", details=details)

class ContractError(P4S4Error):
    pass
class TemporalIntegrityError(P4S4Error):
    pass
class NumericDomainError(P4S4Error):
    pass
