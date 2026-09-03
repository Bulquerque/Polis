"""Canonical execution facade for legacy and registered extension modules."""
from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping
from typing import Any

from ..contracts import ExecutionProfile, ModuleExecutionContext
from ..shared.contracts import ModuleExecutionEnvelope
from .module_contracts import (
    validate_declared_module_metadata,
    validate_module_inputs,
    validate_module_outputs,
)
from .registry import by_id


def _normalize_outputs(result: Mapping[str, Any]) -> dict[str, Any]:
    nested = result.get("outputs")
    return dict(nested) if isinstance(nested, Mapping) else dict(result)


def _context_from_legacy_config(config: Mapping[str, Any] | None) -> ModuleExecutionContext:
    values = dict(config or {})
    raw_profile = str(values.pop("execution_profile", "TEST")).upper()
    profile = ExecutionProfile(raw_profile)
    services = values.pop("services", {})
    if not isinstance(services, Mapping):
        raise TypeError("config.services must be a mapping")
    for key in ("service", "runtime", "provider", "sleep"):
        if key in values:
            services = {**dict(services), key: values[key]}
    return ModuleExecutionContext(profile=profile, config=values, services=services)


async def execute_module_async(
    module_id: str,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
    *,
    context: ModuleExecutionContext | None = None,
) -> ModuleExecutionEnvelope:
    """Execute a registered module through its sole canonical public interface."""
    registration = by_id(module_id)
    module = importlib.import_module(registration.implementation_path)
    validate_declared_module_metadata(module_id, module)
    validate_module_inputs(module_id, inputs, allow_extra=False)
    canonical_entrypoint = getattr(module, "execute", None)
    if not callable(canonical_entrypoint):
        raise TypeError(f"{module_id} does not expose canonical execute(inputs, context)")
    execution_context = context or _context_from_legacy_config(config)
    result = await canonical_entrypoint(dict(inputs), execution_context)
    if not isinstance(result, Mapping):
        raise TypeError(f"{module_id} returned {type(result).__name__}; expected mapping")
    outputs = _normalize_outputs(result)
    validate_module_outputs(module_id, outputs)
    return ModuleExecutionEnvelope(
        module_id=registration.module_id,
        module_name=registration.module_name,
        subphase_id=registration.subphase_id,
        outputs=outputs,
    )


def execute_module(
    module_id: str,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
    *,
    context: ModuleExecutionContext | None = None,
) -> ModuleExecutionEnvelope:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(execute_module_async(module_id, inputs, config, context=context))
    raise RuntimeError("execute_module() cannot run inside an active event loop; use execute_module_async()")
