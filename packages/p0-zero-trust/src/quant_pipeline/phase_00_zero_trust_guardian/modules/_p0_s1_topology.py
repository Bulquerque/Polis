from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s1_artifacts import is_economic_artifact
from ._p0_s1_baseline import architecture_baseline
from ._p0_s1_common import load_mapping_input


def load_connection_matrix(value: Any) -> tuple[dict[str, Any], str]:
    try:
        return load_mapping_input(
            value,
            label="connection matrix",
            collection_key="module_io_matrix",
            symbolic_name="connection_matrix_yaml",
        )
    except ContractValidationError as exc:
        message = str(exc).replace(
            "connection_matrix_yaml must be a mapping",
            "connection_matrix_yaml must be a matrix mapping",
        )
        raise ContractValidationError(message) from exc


def validate_topology(
    matrix: dict[str, Any],
    phases: dict[str, str],
    registered: dict[str, dict[str, str]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    phase_id = _validate_matrix_identity(matrix, phases)
    raw_rows = matrix["module_io_matrix"]
    if not raw_rows or not all(isinstance(row, dict) for row in raw_rows):
        raise ContractValidationError("module_io_matrix must contain module mappings")
    rows = [
        _normalize_row(row, index, phase_id, registered)
        for index, row in enumerate(raw_rows)
    ]
    _validate_phase_coverage(rows, phase_id, registered)
    _validate_artifact_producers(rows)
    connections = _validate_edges(rows)
    _validate_zero_trust_artifacts(rows, phases[phase_id])
    return phase_id, rows, connections


def _validate_matrix_identity(matrix: dict[str, Any], phases: dict[str, str]) -> str:
    expected_fields = {"phase", "rc", "contract", "format", "module_io_matrix"}
    if set(matrix) != expected_fields:
        raise ContractValidationError(
            "connection matrix root must declare exactly " + str(sorted(expected_fields))
        )
    phase_id = matrix["phase"]
    if phase_id not in phases:
        raise ContractValidationError(f"connection matrix declares unknown phase: {phase_id}")
    baseline = architecture_baseline()
    if matrix["rc"] != baseline["rc"] or matrix["contract"] != baseline["matrix"]["contract"]:
        raise ContractValidationError("connection matrix contract identity is incompatible")
    if matrix["format"] != baseline["matrix"]["format"]:
        raise ContractValidationError("connection matrix format is incompatible")
    return str(phase_id)


def _normalize_row(
    row: dict[str, Any],
    index: int,
    phase_id: str,
    registered: dict[str, dict[str, str]],
) -> dict[str, Any]:
    required = {
        "module_id",
        "module_name",
        "subphase",
        "consumes_from",
        "emits_to",
        "module_contract",
    }
    missing = sorted(required.difference(row))
    extra = sorted(set(row).difference(required))
    if missing or extra:
        raise ContractValidationError(
            f"connection matrix row {index} has invalid fields; missing={missing}, extra={extra}"
        )
    module_id = row["module_id"]
    if module_id not in registered:
        raise ContractValidationError(
            f"connection matrix references unknown module_id: {module_id}"
        )
    module = registered[module_id]
    _validate_row_identity(row, module, phase_id)
    normalized = {
        "module_id": module_id,
        "module_name": row["module_name"],
        "subphase": row["subphase"],
        "module_contract": _normalize_contract_path(row["module_contract"], module),
        "consumes_from": _normalize_direction(row, "consumes_from"),
        "emits_to": _normalize_direction(row, "emits_to"),
    }
    return normalized


def _validate_row_identity(
    row: dict[str, Any], module: dict[str, str], phase_id: str
) -> None:
    module_id = str(row["module_id"])
    if module["phase_id"] != phase_id:
        raise ContractValidationError(
            f"connection matrix module is outside declared phase {phase_id}: {module_id}"
        )
    if row["module_name"] != module["module_name"] or row["subphase"] != module["subphase_id"]:
        raise ContractValidationError(
            f"connection matrix identity does not match registry for {module_id}"
        )


def _normalize_contract_path(value: Any, module: dict[str, str]) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(
            f"module_contract does not match registry for {module['module_id']}"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 2 or pure.parts[0] != "modules":
        raise ContractValidationError(
            f"module_contract does not match registry for {module['module_id']}"
        )
    if not module["contract_path"].endswith("/" + pure.as_posix()):
        raise ContractValidationError(
            f"module_contract does not match registry for {module['module_id']}"
        )
    return pure.as_posix()


def _normalize_direction(row: dict[str, Any], direction: str) -> dict[str, list[str]]:
    module_id = str(row["module_id"])
    payload = row[direction]
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{module_id}.{direction} must be a mapping")
    boundary = "phase_inputs" if direction == "consumes_from" else "phase_outputs"
    expected = {"modules", "artifacts", boundary}
    if set(payload) != expected:
        raise ContractValidationError(
            f"{module_id}.{direction} must declare exactly {sorted(expected)}"
        )
    normalized = {
        "modules": _string_list(payload["modules"], f"{module_id}.{direction}.modules"),
        "artifacts": _string_list(payload["artifacts"], f"{module_id}.{direction}.artifacts"),
        boundary: _string_list(payload[boundary], f"{module_id}.{direction}.{boundary}"),
    }
    if not set(normalized[boundary]).issubset(normalized["artifacts"]):
        raise ContractValidationError(
            f"{module_id}.{direction}.{boundary} contains undeclared artifacts"
        )
    return normalized


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{path} must be a list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{path} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractValidationError(f"{path} contains duplicate values")
    return list(value)


def _validate_phase_coverage(
    rows: list[dict[str, Any]],
    phase_id: str,
    registered: dict[str, dict[str, str]],
) -> None:
    ids = [row["module_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ContractValidationError("connection matrix contains duplicate module_id values")
    expected = {
        module_id
        for module_id, module in registered.items()
        if module["phase_id"] == phase_id
    }
    if set(ids) != expected:
        missing = sorted(expected.difference(ids))
        extra = sorted(set(ids).difference(expected))
        raise ContractValidationError(
            f"connection matrix phase coverage mismatch; missing={missing}, extra={extra}"
        )


def _validate_artifact_producers(rows: list[dict[str, Any]]) -> None:
    producer_by_artifact: dict[str, str] = {}
    for row in rows:
        for artifact in row["emits_to"]["artifacts"]:
            previous = producer_by_artifact.get(artifact)
            if previous is not None:
                raise ContractValidationError(
                    f"artifact {artifact} has multiple producers: {previous}, {row['module_id']}"
                )
            producer_by_artifact[artifact] = row["module_id"]


def _validate_edges(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_id = {row["module_id"]: row for row in rows}
    edges: list[dict[str, str]] = []
    for row in rows:
        _validate_consumed_artifacts(row, by_id)
        for target in row["emits_to"]["modules"]:
            _validate_emitted_edge(row, target, by_id)
            edges.append({"source_module": row["module_id"], "target_module": target})
    return sorted(edges, key=lambda edge: (edge["source_module"], edge["target_module"]))


def _validate_consumed_artifacts(
    row: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> None:
    module_id = row["module_id"]
    dependencies = row["consumes_from"]["modules"]
    if module_id in dependencies or module_id in row["emits_to"]["modules"]:
        raise ContractValidationError(f"self connection is forbidden for {module_id}")
    consumed = set(row["consumes_from"]["artifacts"])
    produced_by_dependencies: set[str] = set()
    for dependency in dependencies:
        if dependency not in by_id:
            raise ContractValidationError(
                f"{module_id} consumes from unknown or cross-phase module {dependency}"
            )
        producer = by_id[dependency]
        if module_id not in producer["emits_to"]["modules"]:
            raise ContractValidationError(
                f"connection is not reciprocal: {dependency} -> {module_id}"
            )
        shared = set(producer["emits_to"]["artifacts"]).intersection(consumed)
        if not shared:
            raise ContractValidationError(
                f"connection {dependency} -> {module_id} has no declared shared artifact"
            )
        produced_by_dependencies.update(shared)
    undeclared = consumed - set(row["consumes_from"]["phase_inputs"]) - produced_by_dependencies
    if undeclared:
        raise ContractValidationError(
            f"{module_id} consumes artifacts without declared producer or phase input: {sorted(undeclared)}"
        )


def _validate_emitted_edge(
    row: dict[str, Any],
    target: str,
    by_id: dict[str, dict[str, Any]],
) -> None:
    module_id = row["module_id"]
    if target not in by_id:
        raise ContractValidationError(
            f"{module_id} emits to unknown or cross-phase module {target}"
        )
    consumer = by_id[target]
    if module_id not in consumer["consumes_from"]["modules"]:
        raise ContractValidationError(f"connection is not reciprocal: {module_id} -> {target}")
    if not set(row["emits_to"]["artifacts"]).intersection(consumer["consumes_from"]["artifacts"]):
        raise ContractValidationError(
            f"connection {module_id} -> {target} has no declared shared artifact"
        )


def _validate_zero_trust_artifacts(rows: list[dict[str, Any]], plane: str) -> None:
    if plane != "zero_trust_control":
        return
    economic = sorted(
        {
            artifact
            for row in rows
            for direction in ("consumes_from", "emits_to")
            for artifact in row[direction]["artifacts"]
            if is_economic_artifact(artifact)
        }
    )
    if economic:
        raise ContractValidationError(
            "zero-trust plane contains economic payload artifacts: " + str(economic)
        )
