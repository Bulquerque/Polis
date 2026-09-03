from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._s2_common import (
    created_at,
    find_forbidden_fields,
    load_yaml_mapping,
    stable_digest,
    validate_schema_value,
)
from ._s2_io_compatibility import compatibility, contract_map, matrix_rows, schema_map


REPOSITORY_ROOT = Path(__file__).resolve().parents[6]


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    return load_yaml_mapping(path, label)


def _find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    return find_forbidden_fields(value, path)


def _report(
    name: str,
    payload: dict[str, Any],
    findings: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    numbered = [
        {"finding_id": f"{name.upper()}-{index:04d}", **finding}
        for index, finding in enumerate(findings, start=1)
    ]
    digest = stable_digest({**payload, "findings": numbered})
    return {
        "artifact_id": f"{name.replace('_', '-')}-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        **payload,
        "findings": numbered,
        "finding_count": len(numbered),
        "status": "FAIL" if numbered else "PASS",
        "release_blocking": bool(numbered),
        "validation_evidence_status": (
            "domain_oracle_failed"
            if numbered
            else "domain_oracle_pass_pending_independent_judge"
        ),
        "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")

    required_inputs = ["contract_registry", "schema_registry", "validated_connection_matrix"]
    missing = [name for name in required_inputs if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = _find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")

    (
        contracts,
        schemas,
        rows,
        connections,
        io_checks,
        schema_checks,
        io_findings,
        schema_findings,
    ) = _analyze_compatibility(inputs)

    io_report = _build_io_report(
        inputs,
        contracts,
        rows,
        connections,
        io_checks,
        io_findings,
        config,
    )
    schema_report = _build_schema_report(
        inputs,
        schemas,
        schema_checks,
        schema_findings,
        config,
    )
    outputs = {
        "io_compatibility_report": io_report,
        "schema_compatibility_report": schema_report,
    }
    _validate_outputs(outputs)
    return {
        "module_id": "P0.S2.M03",
        "module_name": "input_output_compatibility_checker",
        "phase": "P0",
        "subphase": "P0.S2",
        "contract": "P0_S2_M03_input_output_compatibility_checker.yaml",
        "required_inputs": required_inputs,
        "outputs": outputs,
    }



def _analyze_compatibility(
    inputs: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    contracts, global_contracts = contract_map(inputs["contract_registry"])
    schemas, mirrors = schema_map(inputs["schema_registry"], repository_root=REPOSITORY_ROOT)
    matrix_phase, rows, connections = matrix_rows(
        inputs["validated_connection_matrix"], contracts
    )
    io_checks, schema_checks, io_findings, schema_findings = compatibility(
        contracts,
        global_contracts,
        schemas,
        mirrors,
        matrix_phase,
        rows,
        repository_root=REPOSITORY_ROOT,
    )
    return (
        contracts,
        schemas,
        rows,
        connections,
        io_checks,
        schema_checks,
        io_findings,
        schema_findings,
    )

def _build_io_report(
    inputs: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    return _report(
        "io_compatibility_report",
        {
            "contract_registry_lineage_id": inputs["contract_registry"]["lineage_id"],
            "connection_matrix_lineage_id": inputs["validated_connection_matrix"]["lineage_id"],
            "checked_contract_count": len(contracts),
            "checked_matrix_module_count": len(rows),
            "checked_matrix_connection_count": len(connections),
            "compatibility_checks": checks,
            "compatible_check_count": sum(item["status"] == "COMPATIBLE" for item in checks),
            "optional_check_count": sum(item["status"] == "OPTIONAL" for item in checks),
            "incompatible_check_count": sum(item["status"] == "INCOMPATIBLE" for item in checks),
            "output_covers_required_input": not findings,
            "optional_feedback_not_blocking": all(
                not item["release_blocking"] for item in checks if item["status"] == "OPTIONAL"
            ),
        },
        findings,
        config,
    )


def _build_schema_report(
    inputs: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    missing_codes = {"REQUIRED_ARTIFACT_SCHEMA_MISSING", "OUTPUT_SCHEMA_BINDING_MISSING"}
    type_codes = {"SCHEMA_SEMANTIC_INCOMPATIBILITY"}
    return _report(
        "schema_compatibility_report",
        {
            "contract_registry_lineage_id": inputs["contract_registry"]["lineage_id"],
            "schema_registry_lineage_id": inputs["schema_registry"]["lineage_id"],
            "checked_authority_schema_count": len(schemas),
            "schema_checks": checks,
            "compatible_schema_count": sum(item["status"] == "COMPATIBLE" for item in checks),
            "incompatible_schema_count": sum(item["status"] == "INCOMPATIBLE" for item in checks),
            "required_fields_compatible": not any(item["code"] in missing_codes for item in findings),
            "required_types_compatible": not any(item["code"] in type_codes for item in findings),
        },
        findings,
        config,
    )


def _validate_outputs(outputs: dict[str, dict[str, Any]]) -> None:
    for artifact_name, artifact in outputs.items():
        schema = _load_yaml_mapping(
            SCHEMA_ROOT / f"{artifact_name}.schema.yaml",
            f"{artifact_name} schema",
        )
        validate_schema_value(artifact, schema, artifact_name)
        leaked = _find_forbidden_fields(artifact, artifact_name)
        if leaked:
            raise ContractValidationError(f"forbidden output fields detected: {leaked}")
