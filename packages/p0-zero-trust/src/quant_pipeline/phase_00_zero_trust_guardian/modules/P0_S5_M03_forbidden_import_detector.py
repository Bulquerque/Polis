from __future__ import annotations

from ._s5_ast_metrics import parse_python
from ._s5_core import envelope, load_mapping, module_result, require_config, require_inputs, source_files
from ._s5_schema import validate_artifact
from ._s5_import_rules import collect_imports, matched_rule


def _scan_entry(entry: dict, policy: dict) -> list[dict]:
    tree = parse_python(entry)
    if tree is None:
        return []
    findings: list[dict] = []
    for line, imported, import_kind in collect_imports(tree):
        rule = matched_rule(entry["path"], imported, policy)
        if rule:
            findings.append({
                "path": entry["path"], "line": line, "import_name": imported,
                "matched_rule": rule, "kind": import_kind,
            })
    return findings


def _policy_patterns(policy: dict) -> list[str]:
    patterns = policy.get("forbidden_imports")
    valid = isinstance(patterns, list) and bool(patterns)
    valid = valid and all(isinstance(item, str) and item for item in patterns)
    if not valid:
        raise ValueError("forbidden import policy must define non-empty forbidden_imports")
    return patterns


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, {"source_tree_manifest", "forbidden_import_policy_yaml"})
    config = require_config(config)
    files = source_files(inputs["source_tree_manifest"])
    policy = load_mapping(inputs["forbidden_import_policy_yaml"], "forbidden import policy")
    patterns = _policy_patterns(policy)

    python_entries = [entry for entry in files if entry["path"].endswith(".py")]
    findings = [finding for entry in python_entries for finding in _scan_entry(entry, policy)]
    python_count = len(python_entries)
    if not python_count:
        raise ValueError("source_tree_manifest contains no Python source")
    findings.sort(key=lambda x: (x["path"], x["line"], x["import_name"]))
    artifact = envelope("forbidden_import_report", {"files": files, "policy": policy, "findings": findings}, config)
    artifact.update({
        "checked_python_file_count": python_count,
        "policy_rule_count": len(patterns),
        "violation_count": len(findings),
        "violations": findings,
        "status": "FAIL" if findings else "PASS",
        "release_blocking": bool(findings),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    })
    validate_artifact(artifact, "forbidden_import_report.schema.yaml", "forbidden_import_report")
    return module_result(
        "P0.S5.M03", "forbidden_import_detector",
        ["source_tree_manifest", "forbidden_import_policy_yaml"], "forbidden_import_report", artifact,
    )
