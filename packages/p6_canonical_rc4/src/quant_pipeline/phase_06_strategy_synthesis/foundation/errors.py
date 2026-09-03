"""Structured P6 errors with stable reason codes and diagnostic context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Phase6Error(Exception):
    message: str
    reason_code: str
    module_id: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.message} | reason_code={self.reason_code} module_id={self.module_id} context={self.context}"


class Phase6ContractError(Phase6Error):
    """Input, output, configuration, or handoff contract violation."""


class Phase6InvariantError(Phase6Error):
    """Internal invariant violation after validated inputs."""
