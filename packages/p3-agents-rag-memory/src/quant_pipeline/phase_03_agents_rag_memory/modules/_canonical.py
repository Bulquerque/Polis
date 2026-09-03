"""Compatibility bridge behind the canonical module entrypoint.

All callers use ``execute(inputs, context)``.  Legacy ``run_module`` functions
remain internal while individual capabilities are progressively simplified.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from ..contracts import ModuleExecutionContext


async def invoke_legacy_entrypoint(
    namespace: Mapping[str, Any],
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> Mapping[str, Any]:
    """Invoke one legacy wrapper without losing dependency injection semantics."""

    payload = dict(inputs)
    config = context.legacy_config()
    async_entrypoint = namespace.get("run_module_async")
    if callable(async_entrypoint):
        signature = inspect.signature(async_entrypoint)
        parameters = signature.parameters
        if "runtime" in parameters and parameters["runtime"].kind is inspect.Parameter.KEYWORD_ONLY:
            runtime = context.services.get("runtime", config.get("runtime"))
            if runtime is None:
                raise TypeError("ModuleExecutionContext.services['runtime'] is required")
            result = await async_entrypoint(payload, runtime=runtime)
        else:
            result = await async_entrypoint(payload, config)
    else:
        entrypoint = namespace.get("run_module")
        if not callable(entrypoint):
            raise TypeError("canonical module wrapper has no legacy implementation")
        result = entrypoint(payload, config)
        if inspect.isawaitable(result):
            result = await result
    if not isinstance(result, Mapping):
        raise TypeError(f"module returned {type(result).__name__}; expected mapping")
    return dict(result)
