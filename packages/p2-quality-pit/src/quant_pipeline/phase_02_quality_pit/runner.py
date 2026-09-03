"""Phase runner.

Executes module wrappers in contract order and returns the evolved context plus a
summary of declared phase outputs.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import yaml

from . import fail_fast

PHASE_NAME = "phase_02_quality_pit"
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = PACKAGE_ROOT / "contracts"
MODULE_ROOT = PACKAGE_ROOT / "modules"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fail_fast(isinstance(data, dict), f"{path.name} must be a YAML mapping")
    return data


def _module_path(contract_filename: str) -> str:
    return f"quant_pipeline.{PHASE_NAME}.modules.{Path(contract_filename).stem}"


def _topological_order(rows: list[dict]) -> list[dict]:
    row_by_id = {row.get("module_id"): row for row in rows}
    index_by_id = {row.get("module_id"): idx for idx, row in enumerate(rows)}
    deps = {
        module_id: [dep for dep in row.get("consumes_from", {}).get("modules", []) if dep in row_by_id]
        for module_id, row in row_by_id.items()
    }
    pending = sorted([module_id for module_id, dep_list in deps.items() if not dep_list], key=index_by_id.get)
    ordered: list[dict] = []
    while pending:
        module_id = pending.pop(0)
        ordered.append(row_by_id[module_id])
        for other_id, dep_list in deps.items():
            if module_id in dep_list:
                dep_list.remove(module_id)
                if not dep_list and row_by_id[other_id] not in ordered and other_id not in pending:
                    pending.append(other_id)
                    pending.sort(key=index_by_id.get)
    fail_fast(len(ordered) == len(rows), "module dependency cycle or unresolved contract reference")
    return ordered


def run_phase(inputs: dict, config: dict) -> dict:
    fail_fast(isinstance(inputs, dict), "inputs must be an explicit dict")
    fail_fast(isinstance(config, dict), "config must be an explicit dict")
    if config.get("strict_physical_validation"):
        fail_fast(
            config.get("profile_id") in {"DAILY_MARK_RESEARCH_BR_V1", "DAILY_MARK_RESEARCH_V1"},
            "strict P2 execution requires profile_id=DAILY_MARK_RESEARCH_BR_V1",
        )

    input_contract = _load_yaml(CONTRACT_ROOT / "INPUT_CONTRACTS.yaml")
    output_contract = _load_yaml(CONTRACT_ROOT / "OUTPUT_CONTRACTS.yaml")
    module_io_matrix = _load_yaml(CONTRACT_ROOT / "MODULE_IO_MATRIX.yaml")

    required_inputs = list(input_contract.get("required_inputs", []))
    missing_inputs = [name for name in required_inputs if name not in inputs]
    fail_fast(not missing_inputs, f"missing required phase inputs: {missing_inputs}")

    context = dict(inputs)
    module_results = []
    ordered_rows = _topological_order(list(module_io_matrix.get("module_io_matrix", [])))

    for row in ordered_rows:
        contract_filename = row.get("module_contract")
        fail_fast(bool(contract_filename), f"missing module contract for {row.get('module_id')}")
        module = import_module(_module_path(contract_filename))
        module_contract = _load_yaml(MODULE_ROOT / Path(contract_filename).name)
        module_required_inputs = list(module_contract.get("inputs", []))
        module_inputs = {name: context[name] for name in module_required_inputs if name in context}
        missing_module_inputs = [name for name in module_required_inputs if name not in module_inputs]
        fail_fast(not missing_module_inputs, f"{contract_filename} missing inputs: {missing_module_inputs}")
        result = module.run_module(module_inputs, config)
        module_results.append(result)
        context.update(result.get("outputs", {}))

    declared_outputs = list(output_contract.get("outputs", []))
    phase_outputs = {name: context[name] for name in declared_outputs if name in context}
    missing_phase_outputs = [name for name in declared_outputs if name not in phase_outputs]
    fail_fast(not missing_phase_outputs, f"missing declared phase outputs: {missing_phase_outputs}")

    return {
        "phase": input_contract.get("phase", PHASE_NAME),
        "validation_mode": "contract_pipeline",
        "required_inputs": required_inputs,
        "received_inputs": sorted(inputs),
        "config_keys": sorted(config),
        "declared_outputs": declared_outputs,
        "module_results": module_results,
        "phase_outputs": phase_outputs,
        "context": context,
    }
