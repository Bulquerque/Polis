from __future__ import annotations

import importlib
import math
from collections.abc import Mapping

from pydantic import JsonValue

from ...contracts import ExecutionProfile, ModuleExecutionContext
from ...orchestration.module_contracts import (
    ModuleContractError,
    validate_declared_module_metadata,
    validate_module_inputs,
    validate_module_outputs,
)
from ..errors import BoundaryValidationError
from .catalog import MODULE_IMPORT_PATHS
from .models import JsonPayload, ModuleExecutionResult, ModuleInvocation


class PythonModuleExecutor:
    """Execute whitelisted modules exclusively through ``execute(inputs, context)``.

    The final release removes legacy entrypoint selection from the production engine. The old
    wrappers remain importable for a deprecation window, but this executor never
    calls them. Inputs and outputs are checked against the canonical module matrix
    and artifact schemas before any artifact is persisted.
    """

    async def execute(self, module_id: str, invocation: ModuleInvocation) -> ModuleExecutionResult:
        try:
            import_path = MODULE_IMPORT_PATHS[module_id]
        except KeyError as exc:
            raise BoundaryValidationError(f"module is not in the runtime whitelist: {module_id}") from exc
        module = importlib.import_module(import_path)
        try:
            validate_declared_module_metadata(module_id, module)
            validate_module_inputs(module_id, invocation.inputs, allow_extra=False)
        except ModuleContractError as exc:
            raise BoundaryValidationError(str(exc)) from exc

        canonical = getattr(module, "execute", None)
        if not callable(canonical):
            raise BoundaryValidationError(f"{module_id} has no canonical execute entrypoint")
        context = self._context(invocation)
        raw = await canonical(dict(invocation.inputs), context)
        if not isinstance(raw, Mapping):
            raise BoundaryValidationError(f"{module_id} returned a non-mapping result")
        candidate = raw.get("outputs", raw)
        if not isinstance(candidate, Mapping):
            raise BoundaryValidationError(f"{module_id} outputs must be a mapping")
        outputs: dict[str, JsonPayload] = {}
        for name, payload in candidate.items():
            if not isinstance(name, str) or not name:
                raise BoundaryValidationError(f"{module_id} emitted an invalid artifact name")
            if not isinstance(payload, Mapping):
                raise BoundaryValidationError(
                    f"{module_id} output {name} must be a JSON object, got {type(payload).__name__}"
                )
            outputs[name] = self._json_object(payload, module_id=module_id, artifact_name=name)
        try:
            validate_module_outputs(module_id, outputs)
        except ModuleContractError as exc:
            raise BoundaryValidationError(str(exc)) from exc
        return ModuleExecutionResult(outputs=outputs)

    @staticmethod
    def _context(invocation: ModuleInvocation) -> ModuleExecutionContext:
        raw_profile = str(invocation.config.get("execution_profile", "TEST")).upper()
        try:
            profile = ExecutionProfile(raw_profile)
        except ValueError as exc:
            raise BoundaryValidationError(f"unsupported execution_profile: {raw_profile}") from exc
        if invocation.runtime is None:
            services: dict[str, object] = {}
        elif isinstance(invocation.runtime, Mapping):
            services = dict(invocation.runtime)
        else:
            services = {"runtime": invocation.runtime}
        return ModuleExecutionContext(profile=profile, config=dict(invocation.config), services=services)

    @classmethod
    def _json_object(cls, value: Mapping[object, object], *, module_id: str, artifact_name: str) -> JsonPayload:
        result: JsonPayload = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise BoundaryValidationError(
                    f"{module_id} output {artifact_name} contains a non-string JSON key"
                )
            result[raw_key] = cls._json_value(raw_value, module_id=module_id, artifact_name=artifact_name)
        return result

    @classmethod
    def _json_value(cls, value: object, *, module_id: str, artifact_name: str) -> JsonValue:
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise BoundaryValidationError(
                    f"{module_id} output {artifact_name} contains a non-finite float"
                )
            return value
        if isinstance(value, Mapping):
            return cls._json_object(value, module_id=module_id, artifact_name=artifact_name)
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item, module_id=module_id, artifact_name=artifact_name) for item in value]
        raise BoundaryValidationError(
            f"{module_id} output {artifact_name} contains non-JSON value {type(value).__name__}"
        )
