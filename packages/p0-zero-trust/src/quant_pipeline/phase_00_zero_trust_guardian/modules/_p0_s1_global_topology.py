from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_baseline import (
    architecture_baseline,
    canonical_module_ids,
    canonical_phase_ids,
)
from ._p0_s1_common import (
    MODULE_ID_PATTERN,
    load_mapping_input,
    normalized_version,
)


def load_io_matrices(value: Any, release_scope: str | None = None) -> list[dict[str, Any]]:
    items = _matrix_items(value)
    p0_scope = str(release_scope or "").upper() == "P0_TECHNICAL_CLOSURE"
    matrices: list[dict[str, Any]] = []
    baseline = architecture_baseline()
    for index, item in enumerate(items):
        matrix, _ = load_mapping_input(
            item,
            label=f"module io matrix {index}",
            collection_key="module_io_matrix",
            symbolic_name=f"module_io_matrix_all_phases[{index}]",
        )
        phase = matrix.get("phase")
        if phase not in canonical_phase_ids():
            raise ContractValidationError(f"invalid or missing phase in IO matrix {index}: {phase}")
        matrix_rc = matrix.get("rc") or matrix.get("version")
        # P4's V14.9 matrix is the supported downstream compatibility
        # contract; all other phases must bind to the active RC baseline.
        p4_compat = phase == "P4" and str(matrix_rc).upper().startswith("V14.9")
        if not p4_compat and normalized_version(matrix_rc) != normalized_version(baseline["rc"]):
            raise ContractValidationError(f"incompatible rc in IO matrix for {phase}")
        modules = matrix.get("module_io_matrix")
        if not isinstance(modules, list) or not modules or not all(isinstance(module, dict) for module in modules):
            raise ContractValidationError(f"IO matrix for {phase} has no materialized modules")
        matrices.append(matrix)
    phases = [matrix["phase"] for matrix in matrices]
    expected_phases = {"P0"} if p0_scope else canonical_phase_ids()
    if len(phases) != len(expected_phases) or set(phases) != expected_phases or len(phases) != len(set(phases)):
        raise ContractValidationError("module_io_matrix_all_phases does not cover the active release scope")
    return matrices


def build_global_topology(matrices: list[dict[str, Any]], release_scope: str | None = None) -> dict[str, Any]:
    modules: dict[str, dict[str, Any]] = {}
    emit_edges: set[tuple[str, str]] = set()
    consume_edges: set[tuple[str, str]] = set()
    produced: dict[str, set[str]] = {}
    consumed: dict[str, set[str]] = {}
    for matrix in matrices:
        _index_matrix(matrix, modules, emit_edges, consume_edges, produced, consumed)
    expected_modules = {
        module_id
        for module_id in canonical_module_ids()
        if str(release_scope or "").upper() != "P0_TECHNICAL_CLOSURE"
        or module_id.startswith("P0.")
    }
    if set(modules) != expected_modules:
        raise ContractValidationError(
            "module_io_matrix_all_phases must cover the active canonical modules"
        )
    return {
        "modules": modules,
        "emit_edges": emit_edges,
        "consume_edges": consume_edges,
        "produced_artifacts": produced,
        "consumed_artifacts": consumed,
    }


def _matrix_items(value: Any) -> list[Any]:
    if isinstance(value, (str, Path)):
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("matrices", "paths", "module_io_matrices"):
            if key in value:
                if not isinstance(value[key], list):
                    raise ContractValidationError(
                        f"module_io_matrix_all_phases.{key} must be a list"
                    )
                return value[key]
        if "module_io_matrix" in value:
            return [value]
        if value and all(isinstance(item, (str, Path, dict)) for item in value.values()):
            return list(value.values())
    raise ContractValidationError(
        "module_io_matrix_all_phases must contain paths or materialized matrices"
    )


def _index_matrix(
    matrix: dict[str, Any],
    modules: dict[str, dict[str, Any]],
    emit_edges: set[tuple[str, str]],
    consume_edges: set[tuple[str, str]],
    produced: dict[str, set[str]],
    consumed: dict[str, set[str]],
) -> None:
    phase = str(matrix["phase"])
    for module in matrix["module_io_matrix"]:
        # P4 V14.9 is an intentionally preserved legacy matrix contract.  It
        # expresses artifact edges as consumes_artifacts/emits_artifacts and
        # does not carry module-to-module edges.  Normalize it at the boundary
        # so the active global topology remains one canonical shape without
        # rewriting the compatibility contract.
        if "consumes_from" not in module and "consumes_artifacts" in module:
            module = dict(module)
            module["consumes_from"] = {
                "modules": list(module.get("consumes_modules", []) or []),
                "artifacts": list(module.get("consumes_artifacts", []) or []),
            }
        if "emits_to" not in module and "emits_artifacts" in module:
            module = dict(module)
            module["emits_to"] = {
                "modules": list(module.get("emits_modules", []) or []),
                "artifacts": list(module.get("emits_artifacts", []) or []),
            }
        module_id = module.get("module_id")
        if not isinstance(module_id, str) or MODULE_ID_PATTERN.fullmatch(module_id) is None:
            raise ContractValidationError(f"invalid module_id in {phase} IO matrix")
        if module_id in modules or not module_id.startswith(phase + "."):
            raise ContractValidationError(f"duplicate or cross-phase module_id: {module_id}")
        consumes = module.get("consumes_from")
        emits = module.get("emits_to")
        if not isinstance(consumes, dict) or not isinstance(emits, dict):
            raise ContractValidationError(f"module {module_id} lacks consumes_from/emits_to")
        modules[module_id] = module
        for source in consumes.get("modules", []) or []:
            if not isinstance(source, str):
                raise ContractValidationError(f"module {module_id} has invalid source module")
            consume_edges.add((source, module_id))
        for target in emits.get("modules", []) or []:
            if not isinstance(target, str):
                raise ContractValidationError(f"module {module_id} has invalid target module")
            emit_edges.add((module_id, target))
        produced[module_id] = set(emits.get("artifacts", []) or [])
        consumed[module_id] = set(consumes.get("artifacts", []) or [])
