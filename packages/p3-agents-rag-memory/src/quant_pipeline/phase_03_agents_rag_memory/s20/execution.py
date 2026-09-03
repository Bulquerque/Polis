"""Execution-profile guards for S20 provider-backed capabilities."""

from __future__ import annotations

from typing import Any

from ..contracts import ExecutionProfile, ModuleExecutionContext
from .errors import S20ContractError


def service(
    context: ModuleExecutionContext,
    name: str,
    *,
    required_in: tuple[ExecutionProfile, ...] = (ExecutionProfile.LIVE,),
) -> Any | None:
    value = context.services.get(name)
    if context.profile in required_in and value is None:
        raise S20ContractError(
            f"S20 requires injected service {name!r} in {context.profile.value} profile"
        )
    return value
