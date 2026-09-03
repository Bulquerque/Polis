from __future__ import annotations


class S24Error(RuntimeError):
    def __init__(self, *, code: str, message: str, module_id: str) -> None:
        super().__init__(f"{module_id}:{code}:{message}")
        self.code = code
        self.message = message
        self.module_id = module_id


class S24ContractError(S24Error):
    pass


class S24InvariantError(S24Error):
    pass


class S24TemporalError(S24Error):
    pass
