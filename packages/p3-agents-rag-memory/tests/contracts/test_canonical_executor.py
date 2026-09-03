from __future__ import annotations

import importlib

import pytest

from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import MODULE_REGISTRY
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.execution.module_executor import PythonModuleExecutor


def test_all_modules_mark_legacy_entrypoint_deprecated() -> None:
    for registration in MODULE_REGISTRY:
        module = importlib.import_module(registration.implementation_path)
        assert module.LEGACY_ENTRYPOINT_DEPRECATED is True
        assert callable(module.execute)


def test_production_executor_source_has_no_legacy_entrypoint_selection() -> None:
    source = importlib.import_module(
        "quant_pipeline.phase_03_agents_rag_memory.runtime_engine.execution.module_executor"
    ).__file__
    text = open(source, encoding="utf-8").read()
    assert 'getattr(module, "run_module"' not in text
    assert 'getattr(module, "run_module_async"' not in text
    assert 'getattr(module, "execute"' in text
