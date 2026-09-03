from __future__ import annotations

from typing import Any

from ._module_executor import ContractValidationError
from ._p0_s7_common import digest, normalize_text, permission_map, permission_names


def skill_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["skill_id"]: item
        for item in registry.get("skills", [])
        if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
    }


def denied_hits(text: str, rules: dict[str, Any]) -> list[str]:
    normalized = normalize_text(text)
    denied = rules.get("denied_directives", [])
    if not isinstance(denied, list) or not all(isinstance(term, str) and term for term in denied):
        raise ContractValidationError("zero_trust_rules.denied_directives invalid")
    hits = []
    for term in denied:
        if normalize_text(term) in normalized:
            hits.append(term)
    return hits


def normalize_prompt(prompt: dict[str, Any], skill: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    required = {"template_id", "skill_id", "phase_scope", "system_prompt"}
    if required.difference(prompt):
        raise ContractValidationError("prompt fields missing")
    skill_phase = skill.get("phase_scope", prompt["phase_scope"])
    if prompt["phase_scope"] != skill_phase:
        raise ContractValidationError("prompt phase_scope does not match skill")

    text = prompt["system_prompt"]
    if not isinstance(text, str) or not text.strip():
        raise ContractValidationError("empty system_prompt")
    hits = denied_hits(text, rules)
    if hits:
        raise ContractValidationError(f"prompt overrides zero trust rules: {hits}")

    raw_skill_permissions = skill.get("permissions", skill.get("permission_names"))
    if raw_skill_permissions is None:
        raw_skill_permissions = ["read"]
    skill_permissions = permission_map(raw_skill_permissions, "skill")
    requested = prompt.get("requested_permissions")
    requested_permissions = skill_permissions if requested is None else permission_map(requested, "prompt")
    escalated = [name for name, allowed in requested_permissions.items() if allowed and not skill_permissions.get(name)]
    if escalated:
        raise ContractValidationError(f"prompt escalates permissions: {escalated}")

    declared_modules = prompt.get("module_scope", skill.get("module_scope", []))
    if not isinstance(declared_modules, list) or not all(isinstance(x, str) for x in declared_modules):
        raise ContractValidationError("prompt module_scope invalid")
    if not set(declared_modules).issubset(set(skill.get("module_scope", []))):
        raise ContractValidationError("prompt module_scope escalates skill scope")

    normalized_text = normalize_text(text)
    return {
        "template_id": prompt["template_id"],
        "skill_id": prompt["skill_id"],
        "skill_version": str(skill.get("skill_version") or "1.0.0"),
        "phase_scope": prompt["phase_scope"],
        "module_scope": sorted(set(declared_modules)),
        "requested_permissions": requested_permissions,
        "permission_names": permission_names(requested_permissions),
        "system_prompt_sha256": digest(text),
        "normalized_prompt_sha256": digest(normalized_text),
        "skill_definition_sha256": digest(skill),
        "status": "PASS",
    }
