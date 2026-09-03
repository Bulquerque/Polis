from __future__ import annotations

import ast
from pathlib import PurePosixPath

from ._s5_ast_metrics import cyclomatic_complexity, node_lines, parse_python, public_function_count
from ._s5_core import envelope, load_mapping, module_result, require_config, require_inputs, source_files
from ._s5_schema import validate_artifact


def _positive_int(policy: dict, canonical: str, legacy: str | None = None) -> int:
    value = policy.get(canonical)
    if value is None and legacy:
        value = policy.get(legacy)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"code quality policy {canonical} must be a positive integer")
    return value


def _limits(policy: dict) -> dict[str, int]:
    return {
        "file": _positive_int(policy, "max_python_file_lines", "max_file_lines"),
        "function": _positive_int(policy, "max_function_lines"),
        "class": _positive_int(policy, "max_class_lines") if "max_class_lines" in policy else 180,
        "public_functions": _positive_int(policy, "max_module_public_functions") if "max_module_public_functions" in policy else 12,
        "complexity": _positive_int(policy, "max_cyclomatic_complexity") if "max_cyclomatic_complexity" in policy else 10,
    }


def _exception_paths(config: dict) -> set[str]:
    entries = config.get("quality_exceptions", [])
    if not isinstance(entries, list):
        raise ValueError("quality_exceptions must be a list")
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not str(entry.get("reason", "")).strip():
            raise ValueError("quality_exceptions require path and non-empty reason")
        paths.add(entry["path"].replace("\\", "/"))
    return paths


def _finding(path: str, symbol: str, kind: str, observed: int, limit: int) -> dict:
    return {"path": path, "symbol": symbol, "kind": kind, "line_count": observed, "limit": limit}


def _file_findings(path: str, content: str, tree: ast.Module, limits: dict[str, int]) -> list[dict]:
    findings: list[dict] = []
    lines = len(content.splitlines())
    if lines > limits["file"]:
        findings.append(_finding(path, "<module>", "FILE_TOO_LONG", lines, limits["file"]))
    public_count = public_function_count(tree)
    if public_count > limits["public_functions"]:
        findings.append(_finding(path, "<module>", "TOO_MANY_PUBLIC_FUNCTIONS", public_count, limits["public_functions"]))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node_lines(node)
            if length > limits["function"]:
                findings.append(_finding(path, node.name, "FUNCTION_TOO_LONG", length, limits["function"]))
            complexity = cyclomatic_complexity(node)
            if complexity > limits["complexity"]:
                findings.append(_finding(path, node.name, "CYCLOMATIC_COMPLEXITY", complexity, limits["complexity"]))
        elif isinstance(node, ast.ClassDef):
            length = node_lines(node)
            if length > limits["class"]:
                findings.append(_finding(path, node.name, "CLASS_TOO_LONG", length, limits["class"]))
    return findings


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, {"source_tree_manifest", "code_quality_policy_yaml"})
    config = require_config(config)
    files = source_files(inputs["source_tree_manifest"])
    policy = load_mapping(inputs["code_quality_policy_yaml"], "code quality policy")
    limits = _limits(policy)
    exceptions = _exception_paths(config)
    findings: list[dict] = []
    python_count = 0
    for entry in files:
        tree = parse_python(entry)
        if tree is None:
            continue
        python_count += 1
        if entry["path"] in exceptions:
            continue
        findings.extend(_file_findings(entry["path"], entry["content"], tree, limits))
    if not python_count:
        raise ValueError("source_tree_manifest contains no Python source")
    findings.sort(key=lambda x: (x["path"], x["symbol"], x["kind"]))
    artifact = envelope("monolith_report", {"files": files, "policy": policy, "findings": findings}, config)
    artifact.update({
        "checked_python_file_count": python_count,
        "file_line_limit": limits["file"],
        "function_line_limit": limits["function"],
        "finding_count": len(findings),
        "findings": findings,
        "status": "FAIL" if findings else "PASS",
        "release_blocking": bool(findings),
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    })
    validate_artifact(artifact, "monolith_report.schema.yaml", "monolith_report")
    return module_result(
        "P0.S5.M02", "monolith_code_detector",
        ["source_tree_manifest", "code_quality_policy_yaml"], "monolith_report", artifact,
    )
