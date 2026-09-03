from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s7_common import PERMISSION_NAMES, permission_map, permission_names, validate_relative_paths


def _legacy_or_policy_list(
    source: Any,
    legacy_key: str,
    policy: dict[str, Any],
    policy_key: str,
) -> list[str]:
    if isinstance(source, dict) and legacy_key in source:
        legacy = source.get(legacy_key)
        if not isinstance(legacy, list) or not legacy or not all(isinstance(x, str) and x for x in legacy):
            raise ContractValidationError(f"{legacy_key} missing")
        return list(legacy)
    value = policy.get(policy_key)
    if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
        raise ContractValidationError(f"governance policy missing {policy_key}")
    return list(value)


def _maximum_permissions(code: Any, policy: dict[str, Any]) -> dict[str, bool]:
    if isinstance(code, dict) and isinstance(code.get("permissions"), (dict, list)):
        return permission_map(code["permissions"], "code_standards.permissions")
    defaults = policy.get("maximum_permissions")
    return permission_map(defaults, "governance.maximum_permissions")


def build_execution_policies(
    templates: list[dict[str, Any]],
    code_standards: Any,
    testing_standards: Any,
    governance: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, bool]]:
    definition_of_done = _legacy_or_policy_list(
        code_standards,
        "definition_of_done",
        governance,
        "required_definition_of_done",
    )
    required_tests = _legacy_or_policy_list(
        testing_standards,
        "required_tests",
        governance,
        "required_tests",
    )
    required_files = _legacy_or_policy_list(
        testing_standards,
        "required_package_files",
        governance,
        "required_package_files",
    )
    required_files = validate_relative_paths(required_files, "required_package_files")
    maximum = _maximum_permissions(code_standards, governance)

    policies: list[dict[str, Any]] = []
    for template in templates:
        legacy_template = {
            "skill_id": template.get("skill_id", template.get("template_id", "legacy-skill")),
            "skill_version": template.get("skill_version", "1.0.0"),
            "phase_scope": template.get("phase_scope", "P0"),
            "module_scope": template.get("module_scope", []),
        }
        raw_requested = template.get("requested_permissions")
        requested = maximum if raw_requested is None else permission_map(raw_requested, "template requested_permissions")
        effective = {
            name: bool(requested.get(name) and maximum.get(name))
            for name in PERMISSION_NAMES
        }
        escalated = [name for name in PERMISSION_NAMES if effective[name] and not maximum.get(name)]
        if escalated:
            raise ContractValidationError(f"effective policy escalates permissions: {escalated}")
        policies.append({
            "policy_id": f"{template['template_id']}--{legacy_template['skill_id']}",
            "template_id": template["template_id"],
            "skill_id": legacy_template["skill_id"],
            "skill_version": legacy_template["skill_version"],
            "phase_scope": legacy_template["phase_scope"],
            "module_scope": list(legacy_template["module_scope"]),
            "effective_permissions": effective,
            "permission_names": permission_names(effective),
            "definition_of_done": list(definition_of_done),
            "required_tests": list(required_tests),
            "required_package_files": list(required_files),
        })
    return policies, definition_of_done, required_tests, maximum
