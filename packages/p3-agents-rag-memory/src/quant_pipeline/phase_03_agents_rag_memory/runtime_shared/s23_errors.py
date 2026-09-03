from __future__ import annotations


class S23Error(RuntimeError):
    def __init__(self, *, code: str, message: str, module_id: str) -> None:
        super().__init__(f"{module_id}:{code}:{message}")
        self.code = code
        self.message = message
        self.module_id = module_id


class S23InvariantError(S23Error):
    pass


class S23TemporalError(S23Error):
    pass


class S23ContractError(S23Error):
    pass
