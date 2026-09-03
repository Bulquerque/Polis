from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s4_test_evidence import digest


def _unique_index(items: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get(key), str) or not item[key]:
            raise ContractValidationError(f"{label}[{index}] has invalid {key}")
        if item[key] in result:
            raise ContractValidationError(f"duplicate {key} in {label}: {item[key]}")
        result[item[key]] = item
    return result


def build_contract_cases(contracts: list[dict[str, Any]], schemas: list[dict[str, Any]], modules: list[dict[str, Any]], mirrors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contract_index = _unique_index(contracts, "module_id", "contracts")
    module_index = _unique_index(modules, "module_id", "modules")
    if set(contract_index) != set(module_index):
        missing_contracts = sorted(set(module_index).difference(contract_index))
        missing_modules = sorted(set(contract_index).difference(module_index))
        raise ContractValidationError(f"contract/module registry identities differ: contracts_missing={missing_contracts}, modules_missing={missing_modules}")
    schema_paths = set()
    for label, entries in (("schemas", schemas), ("mirrors", mirrors)):
        for index, item in enumerate(entries):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
                raise ContractValidationError(f"{label}[{index}] has invalid path")
            schema_paths.add(item["path"])
    cases = []
    for module_id, contract in sorted(contract_index.items()):
        required = {"inputs", "outputs", "consumes_from", "emits_to", "output_schemas"}
        missing = sorted(required.difference(contract))
        if missing:
            raise ContractValidationError(f"contract {module_id} missing fields: {missing}")
        consumes = contract["consumes_from"]
        emits = contract["emits_to"]
        if not isinstance(consumes, dict) or not isinstance(emits, dict):
            raise ContractValidationError(f"contract {module_id} connections must be mappings")
        bindings = contract["output_schemas"]
        if not isinstance(bindings, list):
            raise ContractValidationError(f"contract {module_id} output_schemas must be a list")
        checks = {
            "io_matches_connections": contract["inputs"] == consumes.get("artifacts") and contract["outputs"] == emits.get("artifacts"),
            "output_schema_count_matches": len(contract["outputs"]) == len(bindings),
            "output_schemas_registered": all(isinstance(binding, dict) and binding.get("schema_path") in schema_paths for binding in bindings),
            "connections_reference_modules": all(peer in module_index for peer in list(consumes.get("modules", [])) + list(emits.get("modules", []))),
        }
        contract_digest = digest(contract)
        for check, passed in checks.items():
            cases.append({
                "case_id": f"{module_id}:{check}",
                "module_id": module_id,
                "check": check,
                "test_class": "CONTRACT_ORACLE",
                "criticality": "CRITICAL",
                "source_contract_digest": f"sha256:{contract_digest}",
                "status": "PASS" if passed else "FAIL",
                "critical": True,
            })
    return cases
