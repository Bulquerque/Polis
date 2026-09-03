from __future__ import annotations

from ._s5_ast_metrics import parse_python
from ._s5_core import envelope, load_mapping, module_result, require_config, require_inputs, source_files
from ._s5_state_analysis import analyze_module_state
from ._s5_schema import validate_artifact


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, {"source_tree_manifest", "code_quality_policy_yaml"})
    config = require_config(config)
    files = source_files(inputs["source_tree_manifest"])
    policy = load_mapping(inputs["code_quality_policy_yaml"], "code quality policy")
    allow = policy.get("allowed_module_globals", [])
    if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
        raise ValueError("allowed_module_globals must be a list of names")

    findings: list[dict] = []
    python_count = 0
    for entry in files:
        tree = parse_python(entry)
        if tree is None:
            continue
        python_count += 1
        findings.extend(analyze_module_state(tree, entry["path"], policy))
    if not python_count:
        raise ValueError("source_tree_manifest contains no Python source")
    findings.sort(key=lambda x: (x["path"], x["line"], x["symbol"], x["kind"]))
    artifact = envelope("hidden_global_state_report", {"files": files, "policy": policy, "findings": findings}, config)
    artifact.update({
        "checked_python_file_count": python_count,
        "violation_count": len(findings),
        "violations": findings,
        "status": "FAIL" if findings else "PASS",
        "release_blocking": bool(findings),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    })
    validate_artifact(artifact, "hidden_global_state_report.schema.yaml", "hidden_global_state_report")
    return module_result(
        "P0.S5.M04", "hidden_global_state_detector",
        ["source_tree_manifest", "code_quality_policy_yaml"], "hidden_global_state_report", artifact,
    )
