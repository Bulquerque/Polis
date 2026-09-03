from __future__ import annotations

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s7_common import (
    created_at, digest, envelope, ensure_unique, list_field,
    load_mapping, reject_forbidden, validate_upstream,
)
from ._p0_s7_prompts import normalize_prompt, skill_index


def run_module(inputs: dict, config: dict | None = None) -> dict:
    required = ["agent_prompt_templates", "agent_skill_registry", "zero_trust_rules"]
    if not isinstance(inputs, dict) or any(name not in inputs for name in required):
        raise ContractValidationError("missing required P0.S7.M02 inputs")
    config = config or {}
    reject_forbidden(inputs)

    prompts_doc, source, source_hash = load_mapping(inputs[required[0]], required[0])
    registry, _, registry_hash = load_mapping(inputs[required[1]], required[1])
    rules, _, rules_hash = load_mapping(inputs[required[2]], required[2])
    validate_upstream(registry, required[1])

    prompts = list_field(prompts_doc, "templates", required[0])
    ensure_unique(prompts, "template_id", "templates")
    skills = skill_index(registry)
    normalized = []
    for prompt in prompts:
        skill = skills.get(prompt.get("skill_id"))
        if skill is None:
            raise ContractValidationError("prompt scope or skill invalid")
        normalized.append(normalize_prompt(prompt, skill, rules))
    normalized.sort(key=lambda item: item["template_id"])

    body = {
        "templates": normalized,
        "source_path": source,
        "source_sha256": source_hash,
        "rules_sha256": rules_hash,
        "skill_registry_sha256": registry_hash,
        "skill_registry_lineage_id": registry.get("lineage_id"),
    }
    lineage = digest(body)
    artifact = {
        "artifact_id": f"validated-prompts-{lineage[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{lineage}",
        **body,
        "template_count": len(normalized),
        "status": "PASS",
        "release_blocking": False,
        "promotion_blocked": True,
    }
    return envelope(
        "P0.S7.M02", "agent_prompt_template_validator",
        "P0_S7_M02_agent_prompt_template_validator.yaml", required,
        "validated_agent_prompt_templates", artifact,
    )
