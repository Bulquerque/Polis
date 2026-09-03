from __future__ import annotations

import ast
import re
from typing import Any

_SECRET_NAME = re.compile(r"(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|access[_-]?key)", re.I)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/(?:home|Users|etc|opt|var|srv|root|tmp)/)")
_MUTATING_METHODS = frozenset({"append", "extend", "insert", "update", "add", "remove", "pop", "clear", "setdefault", "__setitem__"})
_STATEFUL_NAMES = frozenset({"Session", "Client", "Cache", "Pool", "Engine", "Connection", "Executor"})


def _target_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


def _mutable_literal(value: ast.AST | None) -> bool:
    literals = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
    if isinstance(value, literals):
        return True
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in {"list", "dict", "set", "defaultdict"}


def _call_name(value: ast.AST | None) -> str | None:
    if not isinstance(value, ast.Call):
        return None
    if isinstance(value.func, ast.Name):
        return value.func.id
    return value.func.attr if isinstance(value.func, ast.Attribute) else None


def _looks_secret(name: str, value: str) -> bool:
    if not _SECRET_NAME.search(name):
        return False
    safe_suffixes = ("_ENV", "_ENV_NAME", "_VAR", "_VAR_NAME", "_VARIABLE", "_VARIABLE_NAME")
    return not name.upper().endswith(safe_suffixes) and _ENV_NAME.fullmatch(value) is None and bool(value.strip())


def _assignment_findings(node: ast.Assign | ast.AnnAssign, path: str, allow: set[str], stateful: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name in _target_names(node):
        if name in allow:
            continue
        value = node.value
        if _mutable_literal(value):
            findings.append({"path": path, "line": node.lineno, "symbol": name, "kind": "MUTABLE_MODULE_GLOBAL"})
        if _call_name(value) in stateful:
            findings.append({"path": path, "line": node.lineno, "symbol": name, "kind": "IMPORT_TIME_STATEFUL_OBJECT"})
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            if _looks_secret(name, value.value):
                findings.append({"path": path, "line": node.lineno, "symbol": name, "kind": "HARDCODED_SECRET"})
            if _ABSOLUTE_PATH.search(value.value):
                findings.append({"path": path, "line": node.lineno, "symbol": name, "kind": "HARDCODED_ABSOLUTE_PATH"})
    return findings


def _module_mutation(node: ast.stmt, path: str, allow: set[str]) -> list[dict[str, Any]]:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Attribute):
        return []
    owner = node.value.func.value
    if not isinstance(owner, ast.Name) or node.value.func.attr not in _MUTATING_METHODS or owner.id in allow:
        return []
    return [{"path": path, "line": node.lineno, "symbol": owner.id, "kind": "MODULE_LEVEL_MUTATION"}]


def _global_findings(tree: ast.Module, path: str, allow: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            findings.extend(
                {"path": path, "line": node.lineno, "symbol": name, "kind": "GLOBAL_STATEMENT_MUTATION"}
                for name in node.names if name not in allow
            )
    return findings


def analyze_module_state(tree: ast.Module, path: str, policy: dict[str, Any]) -> list[dict[str, Any]]:
    allow = set(policy.get("allowed_module_globals", []))
    stateful = set(policy.get("stateful_constructor_names", _STATEFUL_NAMES))
    findings: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            findings.extend(_assignment_findings(node, path, allow, stateful))
        findings.extend(_module_mutation(node, path, allow))
    findings.extend(_global_findings(tree, path, allow))
    return findings
