"""Canonical entrypoint for P5.S4.M02."""
from __future__ import annotations

from ..context import P5ExecutionContext
from ..domain.core import ModuleRequest, ModuleResult
from ..orchestration.executor import execute_module

MODULE_ID = "P5.S4.M02"


def run_module(request: ModuleRequest, context: P5ExecutionContext) -> ModuleResult:
    if request.module_id != MODULE_ID:
        raise ValueError(f"request module_id {request.module_id} does not match {MODULE_ID}")
    return execute_module(request, context)
