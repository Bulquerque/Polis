"""Fail-closed canonical execution for all P5 modules."""
from __future__ import annotations

from pydantic import ValidationError

from ..context import P5ExecutionContext
from ..domain.core import ErrorRecord, ModuleRequest, ModuleResult, ModuleStatus
from ..errors import (
    ActionNotAllowedError,
    CapabilityUnavailableError,
    ContractError,
    ExecutionModeError,
    MissingInputError,
    P5Error,
    UnknownModuleError,
)
from ..registry import get_module
from ..services.identifiers import stable_hash, stable_id
from .handlers import HANDLERS


def execute_module(request: ModuleRequest, context: P5ExecutionContext) -> ModuleResult:
    context.recorder.emit(
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        module_id=request.module_id,
        event_type="MODULE_START",
        status="RUNNING",
        details={"action": request.action.value, "mode": context.mode.value},
    )
    try:
        try:
            descriptor = get_module(request.module_id)
        except KeyError as exc:
            raise UnknownModuleError(str(exc)) from exc
        _validate_execution(request, context, descriptor)
        payload = _resolve_payload(request, context)
        outcome = HANDLERS[request.module_id](payload, request, context)
        result = _materialize(
            request, descriptor.outputs, outcome, context
        )
    except CapabilityUnavailableError as exc:
        result = ModuleResult(
            module_id=request.module_id,
            status=ModuleStatus.SKIPPED,
            warnings=(str(exc),),
            diagnostics={"code": getattr(exc, "reason_code", None) or exc.code},
        )
    except (ContractError, ValidationError) as exc:
        result = _error_result(request.module_id, ModuleStatus.REJECTED, exc)
    except P5Error as exc:
        result = _error_result(request.module_id, ModuleStatus.FAILED, exc)
    except Exception as exc:  # boundary containment; never converted to success
        result = _error_result(request.module_id, ModuleStatus.FAILED, exc)
    context.recorder.emit(
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        module_id=request.module_id,
        event_type="MODULE_END",
        status=result.status.value,
        details={"outputs": sorted(result.outputs), "errors": len(result.errors)},
    )
    return result


def _validate_execution(request: ModuleRequest, context: P5ExecutionContext, descriptor) -> None:
    if request.action not in descriptor.allowed_actions:
        raise ActionNotAllowedError(
            f"{request.module_id} does not allow action {request.action.value}; "
            f"allowed={tuple(action.value for action in descriptor.allowed_actions)}"
        )
    if context.mode not in descriptor.allowed_modes:
        raise ExecutionModeError(
            f"{request.module_id} cannot run in mode {context.mode.value}; "
            f"allowed={tuple(mode.value for mode in descriptor.allowed_modes)}"
        )
    available = set(request.payload) | set(request.input_artifacts)
    missing = sorted(set(descriptor.required_inputs) - available)
    if missing:
        raise MissingInputError(f"{request.module_id} missing required inputs: {missing}")


def _resolve_payload(request: ModuleRequest, context: P5ExecutionContext) -> dict:
    payload = dict(request.payload)
    references: dict[str, dict] = {}
    for name, reference in request.input_artifacts.items():
        payload[name] = context.artifact_store.read(reference)
        references[name] = reference.model_dump(mode="json")
    payload["__input_references__"] = references
    return payload


def _materialize(request, output_names, outcome, context) -> ModuleResult:
    module_id = request.module_id
    if outcome.status is ModuleStatus.SKIPPED:
        if outcome.values:
            raise ContractError("skipped handler cannot produce values")
        return ModuleResult(
            module_id=module_id,
            status=ModuleStatus.SKIPPED,
            warnings=outcome.warnings or ("capability not active",),
            diagnostics=outcome.diagnostics,
        )
    if len(outcome.values) != len(output_names):
        raise ContractError(
            f"{module_id} produced {len(outcome.values)} values for {len(output_names)} outputs"
        )
    outputs = {}
    for name, value in zip(output_names, outcome.values, strict=True):
        _validate_output_value(name, value)
        input_hashes = _input_hashes(request)
        outputs[name] = context.artifact_store.write(
            name,
            value,
            metadata={
                "phase_id": "P5", "module_id": module_id,
                "module_action": request.action.value,
                "execution_mode": context.mode.value,
                "run_id": context.run_id, "cycle_id": context.cycle_id,
                "pipeline_version": context.identity.pipeline_version,
                "as_of_time": context.as_of_time.isoformat(),
                "created_at": context.generated_at.isoformat(),
                "lineage_id": stable_id(
                    "artifact-lineage", context.run_id, context.cycle_id,
                    module_id, name, input_hashes,
                ),
                "input_hashes": input_hashes,
            },
        )
    return ModuleResult(
        module_id=module_id,
        status=outcome.status,
        outputs=outputs,
        warnings=outcome.warnings,
        diagnostics=outcome.diagnostics,
    )


def _input_hashes(request: ModuleRequest) -> dict[str, str]:
    hashes = {
        f"artifact:{name}": reference.content_hash
        for name, reference in sorted(request.input_artifacts.items())
    }
    hashes.update({
        f"payload:{name}": stable_hash(value)
        for name, value in sorted(request.payload.items())
    })
    return hashes


def _validate_output_value(name: str, value) -> None:
    if value is None:
        raise ContractError(f"output {name} is None")
    if isinstance(value, dict) and not value:
        raise ContractError(f"output {name} is an empty object")
    if isinstance(value, dict) and "records" in value and not value["records"]:
        if value.get("availability") != "UNAVAILABLE" and not value.get("status"):
            raise ContractError(f"output {name} contains empty records without explicit unavailability")


def _error_result(module_id: str, status: ModuleStatus, exc: Exception) -> ModuleResult:
    code = getattr(exc, "reason_code", None) or getattr(exc, "code", "P5-UNEXPECTED-001")
    return ModuleResult(
        module_id=module_id,
        status=status,
        errors=(ErrorRecord(
            code=code,
            message=str(exc),
            details={"exception_type": type(exc).__name__},
        ),),
    )
