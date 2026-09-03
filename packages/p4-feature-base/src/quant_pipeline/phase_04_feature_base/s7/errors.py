from __future__ import annotations
from ..runtime.domain_error import P4DomainError

class P4S7Error(P4DomainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, module_id="P4.S7")
