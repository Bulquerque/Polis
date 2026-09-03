"""Executable positive/negative contract checks for every P3 module."""
from __future__ import annotations

import importlib

import pytest

from quant_pipeline.phase_03_agents_rag_memory.orchestration.module_contracts import (
    ModuleContractError,
    contract_for,
    validate_declared_module_metadata,
    validate_module_inputs,
    validate_module_outputs,
)
from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import MODULE_REGISTRY

MODULES = tuple(MODULE_REGISTRY)


def _inputs(module_id: str) -> dict[str, object]:
    return {name: {} for name in contract_for(module_id).required_inputs}


def _outputs(module_id: str) -> dict[str, object]:
    return {name: {} for name in contract_for(module_id).produced_outputs}


@pytest.mark.parametrize("registration", MODULES, ids=lambda item: item.module_id)
def test_module_metadata_and_positive_contract_sets(registration) -> None:
    module = importlib.import_module(registration.implementation_path)
    validate_declared_module_metadata(registration.module_id, module)
    validate_module_inputs(registration.module_id, _inputs(registration.module_id), validate_payloads=False)
    validate_module_outputs(registration.module_id, _outputs(registration.module_id), validate_payloads=False)


@pytest.mark.parametrize("registration", MODULES, ids=lambda item: item.module_id)
def test_module_rejects_missing_input(registration) -> None:
    values = _inputs(registration.module_id)
    required = contract_for(registration.module_id).required_inputs
    assert required
    values.pop(required[0])
    with pytest.raises(ModuleContractError, match="missing required inputs"):
        validate_module_inputs(registration.module_id, values, validate_payloads=False)


@pytest.mark.parametrize("registration", MODULES, ids=lambda item: item.module_id)
def test_module_rejects_output_set_drift(registration) -> None:
    values = _outputs(registration.module_id)
    produced = contract_for(registration.module_id).produced_outputs
    assert produced
    values.pop(produced[0])
    values["undeclared_test_output"] = {}
    with pytest.raises(ModuleContractError, match="output set mismatch"):
        validate_module_outputs(registration.module_id, values, validate_payloads=False)
