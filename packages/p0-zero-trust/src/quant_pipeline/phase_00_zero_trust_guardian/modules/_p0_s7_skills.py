from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s7_common import permission_map, permission_names, validate_relative_paths


def registry_indexes(phases: dict[str, Any], modules: dict[str, Any]) -> tuple[set[str], dict[str, str]]:
    phase_ids = {
        item.get("phase_id")
        for item in phases.get("phases", [])
        if isinstance(item, dict) and isinstance(item.get("phase_id"), str)
    }
    module_phase: dict[str, str] = {}
    for item in modules.get("modules", []):
        if not isinstance(item, dict) or not isinstance(item.get("module_id"), str):
            continue
        module_id = item["module_id"]
        phase_id = item.get("phase_id") or module_id.split(".", 1)[0]
        module_phase[module_id] = str(phase_id)
    return phase_ids, module_phase


def normalize_skill(
    skill: dict[str, Any],
    phase_ids: set[str],
    module_phase: dict[str, str],
) -> dict[str, Any]:
    required = {"skill_id", "phase_scope", "module_scope", "permissions", "allowed_paths"}
    missing = required.difference(skill)
    if missing:
        raise ContractValidationError(f"skill {skill.get('skill_id')} missing fields: {sorted(missing)}")

    skill_id = skill["skill_id"]
    phase_scope = skill["phase_scope"]
    if not isinstance(skill_id, str) or not skill_id:
        raise ContractValidationError("skill_id must be non-empty")
    if phase_scope not in phase_ids:
        raise ContractValidationError("unknown phase_scope")

    module_scope = skill["module_scope"]
    if not isinstance(module_scope, list) or not module_scope or not all(isinstance(x, str) for x in module_scope):
        raise ContractValidationError("invalid module_scope")
    unknown = sorted(set(module_scope).difference(module_phase))
    if unknown:
        raise ContractValidationError(f"invalid module_scope: unknown modules {unknown}")
    cross_phase = [module_id for module_id in module_scope if module_phase[module_id] != phase_scope]
    if cross_phase and skill.get("cross_phase_scope") is not True:
        raise ContractValidationError(f"module_scope escapes phase_scope: {cross_phase}")

    permissions = permission_map(skill["permissions"], f"skill {skill_id}")
    paths = validate_relative_paths(skill["allowed_paths"], f"skill {skill_id}.allowed_paths")
    capabilities = skill.get("capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(x, str) and x for x in capabilities):
        raise ContractValidationError("invalid capabilities")

    version = str(skill.get("skill_version") or "1.0.0")
    return {
        "skill_id": skill_id,
        "skill_version": version,
        "phase_scope": phase_scope,
        "module_scope": sorted(set(module_scope)),
        "capabilities": sorted(set(capabilities)),
        "permissions": permissions,
        "permission_names": permission_names(permissions),
        "allowed_paths": paths,
        "cross_phase_scope": bool(skill.get("cross_phase_scope", False)),
    }
