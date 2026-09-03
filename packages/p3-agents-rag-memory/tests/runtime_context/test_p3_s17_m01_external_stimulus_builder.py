from __future__ import annotations

import importlib

import pytest

from quant_pipeline.phase_03_agents_rag_memory.s17.errors import (
    ForbiddenFieldError,
    TemporalViolationError,
)
from .s17_test_support import deep_copy_inputs


def _module():
    return importlib.import_module(
        "quant_pipeline.phase_03_agents_rag_memory.modules."
        "P3_S17_M01_external_stimulus_builder"
    )


def test_m01_materializes_deterministic_pit_safe_stimulus(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    first = _module().run_module(inputs)
    second = _module().run_module(inputs)
    assert first == second
    assert first["status"] == "READY"
    assert first["items"][0]["available_at"] <= first["as_of"]
    assert first["items"][0]["evidence_refs"] == ["evidence:apple-test"]


def test_m01_rejects_future_available_at(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    inputs["pit_validated_context"]["records"][0]["available_at"] = "2026-07-27T15:00:00Z"
    with pytest.raises(TemporalViolationError):
        _module().run_module(inputs)


def test_m01_rejects_recursive_forbidden_field(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    inputs["pit_validated_context"]["records"][0]["future_return"] = 0.25
    with pytest.raises(ForbiddenFieldError):
        _module().run_module(inputs)


def test_m01_does_not_mutate_inputs(plan_root) -> None:
    import copy
    inputs = deep_copy_inputs(plan_root)
    original = copy.deepcopy(inputs)
    _module().run_module(inputs)
    assert inputs == original


def test_m01_rejects_duplicate_stimulus_identity(plan_root) -> None:
    inputs = deep_copy_inputs(plan_root)
    duplicate = dict(inputs["pit_validated_context"]["records"][0])
    inputs["pit_validated_context"]["records"].append(duplicate)
    from quant_pipeline.phase_03_agents_rag_memory.s17.errors import InputContractError
    with pytest.raises(InputContractError, match="Duplicate external stimulus identity"):
        _module().run_module(inputs)
