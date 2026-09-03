from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from pydantic import ValidationError
from .economic_errors import ContractError
from .economic_models import ExecutionContext
from .perspective_models import PerspectiveExecutionRegistry


def parse_registry_and_context(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> tuple[PerspectiveExecutionRegistry,ExecutionContext]:
    try:
        registry=PerspectiveExecutionRegistry.model_validate(inputs["approved_hypothesis_passport_registry"])
        context=ExecutionContext.model_validate(config)
    except KeyError as exc:
        raise ContractError("P4_S5_INPUT_MISSING",f"missing required input: {exc.args[0]}") from exc
    except ValidationError as exc:
        raise ContractError("P4_S5_SCHEMA_INVALID","S5 input validation failed",details={"errors":exc.errors(include_url=False)}) from exc
    if registry.run_id!=context.run_id or registry.cycle_id!=context.cycle_id or registry.as_of_time!=context.as_of_time:
        raise ContractError("P4_S5_CONTEXT_MISMATCH","registry and execution context do not match")
    return registry,context
