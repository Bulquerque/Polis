"""Public programmatic API for P5."""
from __future__ import annotations

from .context import P5ExecutionContext
from .domain.core import ModuleRequest, ModuleResult
from .orchestration.executor import execute_module


def run_module(request: ModuleRequest, context: P5ExecutionContext) -> ModuleResult:
    """Run one canonical P5 module through the fail-closed executor."""
    return execute_module(request, context)
