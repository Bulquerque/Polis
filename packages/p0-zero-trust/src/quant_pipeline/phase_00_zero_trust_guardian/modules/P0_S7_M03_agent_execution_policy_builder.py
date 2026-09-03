from __future__ import annotations

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s7_common import (
    created_at, digest, envelope, load_document, load_local_spec,
    load_mapping, reject_forbidden, validate_upstream,
)
from ._p0_s7_policy import build_execution_policies


def run_module(inputs: dict, config: dict | None = None) -> dict:
    required = ["validated_agent_prompt_templates", "code_standards", "testing_standards"]
    if not isinstance(inputs, dict) or any(name not in inputs for name in required):
        raise ContractValidationError("missing required P0.S7.M03 inputs")
    config = config or {}
    reject_forbidden(inputs)

    prompts, _, prompts_hash = load_mapping(inputs[required[0]], required[0])
    code, code_path, code_hash = load_document(inputs[required[1]], required[1])
    tests, test_path, test_hash = load_document(inputs[required[2]], required[2])
    governance, governance_hash = load_local_spec("P0_S7_AGENT_GOVERNANCE_POLICY.spec.yaml")
    validate_upstream(prompts, required[0])
    templates = prompts.get("templates")
    if prompts.get("status") != "PASS" or not isinstance(templates, list) or not templates:
        raise ContractValidationError("prompts are not validated")

    policies, definition_of_done, required_tests, maximum_permissions = build_execution_policies(
        templates, code, tests, governance,
    )
    required_files = policies[0]["required_package_files"]
    body = {
        "prompt_templates_sha256": prompts_hash,
        "code_standards": {"path": code_path, "sha256": code_hash},
        "testing_standards": {"path": test_path, "sha256": test_hash},
        "governance_policy_sha256": governance_hash,
        "governance_policy_version": governance.get("policy_version"),
        "definition_of_done": definition_of_done,
        "required_tests": required_tests,
        "required_package_files": required_files,
        "permissions": maximum_permissions,
        "policies": policies,
        "package_limits": governance.get("package_limits", {}),
        "require_agent_manifest": bool(governance.get("require_agent_manifest", True)),
        "policy_id": governance.get("policy_id"),
    }
    lineage = digest(body)
    artifact = {
        "artifact_id": f"agent-execution-policy-{lineage[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{lineage}",
        **body,
        "policy_count": len(policies),
        "status": "PASS",
        "release_blocking": False,
        "promotion_blocked": True,
    }
    return envelope(
        "P0.S7.M03", "agent_execution_policy_builder",
        "P0_S7_M03_agent_execution_policy_builder.yaml", required,
        "agent_execution_policy", artifact,
    )
