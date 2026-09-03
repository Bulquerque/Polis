from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class S22Issue:
    code: str
    message: str
    module_id: str
    details: Mapping[str, object]


class S22Error(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        module_id: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.issue = S22Issue(
            code=code,
            message=message,
            module_id=module_id,
            details=details or {},
        )
        super().__init__(f"{module_id}:{code}: {message}")


class S22InputError(S22Error):
    pass


class S22InvariantError(S22Error):
    pass


class S22TemporalError(S22Error):
    pass
