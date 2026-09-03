from __future__ import annotations

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s7_common import (
    created_at, digest, envelope, ensure_unique, list_field,
    load_mapping, reject_forbidden, validate_upstream,
)
from ._p0_s7_skills import normalize_skill, registry_indexes


def run_module(inputs: dict, config: dict | None = None) -> dict:
    required = ["agent_skill_definitions_yaml", "validated_phase_registry", "validated_module_registry"]
    if not isinstance(inputs, dict) or any(name not in inputs for name in required):
        raise ContractValidationError("missing required P0.S7.M01 inputs")
    config = config or {}
    reject_forbidden(inputs)

    definitions, source, source_hash = load_mapping(inputs[required[0]], required[0])
    phases, _, _ = load_mapping(inputs[required[1]], required[1])
    modules, _, _ = load_mapping(inputs[required[2]], required[2])
    validate_upstream(phases, required[1])
    validate_upstream(modules, required[2])

    skills = list_field(definitions, "skills", required[0])
    ensure_unique(skills, "skill_id", "skills")
    phase_ids, module_phase = registry_indexes(phases, modules)
    normalized = [normalize_skill(skill, phase_ids, module_phase) for skill in skills]
    normalized.sort(key=lambda item: (item["skill_id"], item["skill_version"]))

    body = {
        "skills": normalized,
        "source_path": source,
        "source_sha256": source_hash,
        "phase_registry_lineage_id": phases.get("lineage_id"),
        "module_registry_lineage_id": modules.get("lineage_id"),
    }
    lineage = digest(body)
    artifact = {
        "artifact_id": f"agent-skill-registry-{lineage[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{lineage}",
        **body,
        "skill_count": len(normalized),
        "status": "PASS",
        "release_blocking": False,
        "promotion_blocked": True,
    }
    return envelope(
        "P0.S7.M01", "agent_skill_registry_builder",
        "P0_S7_M01_agent_skill_registry_builder.yaml", required,
        "agent_skill_registry", artifact,
    )
