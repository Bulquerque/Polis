from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class S21Issue:
    code: str
    message: str
    module_id: str
    details: Mapping[str, object]


class S21Error(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        module_id: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.issue = S21Issue(
            code=code,
            message=message,
            module_id=module_id,
            details=details or {},
        )
        super().__init__(f"{module_id}:{code}: {message}")


class S21InputError(S21Error):
    pass


class S21ContractError(S21Error):
    pass


class S21DependencyError(S21Error):
    pass
