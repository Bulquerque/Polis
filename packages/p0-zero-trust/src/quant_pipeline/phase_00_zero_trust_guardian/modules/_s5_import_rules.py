from __future__ import annotations

import ast
import fnmatch
from typing import Any

from ._s5_ast_metrics import infer_phase_from_path


def _matches(name: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(name, pattern) or name == pattern.rstrip(".*")


def _relative_name(node: ast.ImportFrom) -> str:
    return "." * int(node.level or 0) + (node.module or "")


def _dynamic_import(node: ast.Call) -> str | None:
    is_builtin = isinstance(node.func, ast.Name) and node.func.id == "__import__"
    is_importlib = isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
    if not (is_builtin or is_importlib) or not node.args:
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _node_imports(node: ast.AST) -> list[tuple[int, str, str]]:
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name, "IMPORT") for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [(node.lineno, _relative_name(node), "IMPORT_FROM")]
    if isinstance(node, ast.Call):
        name = _dynamic_import(node)
        return [(getattr(node, "lineno", 1), name, "DYNAMIC_IMPORT")] if name else []
    return []


def collect_imports(tree: ast.Module) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        found.extend(_node_imports(node))
    return found


def _target_phase(import_name: str) -> str | None:
    for number in range(10):
        tokens = (f"quant_pipeline.phase_{number:02d}_", f".phase_{number:02d}_")
        if any(token in import_name for token in tokens):
            return f"P{number}"
    return None


def architecture_violation(path: str, import_name: str) -> str | None:
    source_phase = infer_phase_from_path(path)
    if not source_phase or import_name.startswith(".") or import_name.startswith("quant_pipeline.common"):
        return None
    target_phase = _target_phase(import_name)
    if target_phase and target_phase != source_phase:
        return f"CROSS_PHASE_INTERNAL_IMPORT:{source_phase}->{target_phase}"
    return None


def matched_rule(path: str, import_name: str, policy: dict[str, Any]) -> str | None:
    patterns = policy.get("forbidden_imports", [])
    if not isinstance(patterns, list) or not patterns or not all(isinstance(x, str) and x for x in patterns):
        raise ValueError("forbidden import policy must define non-empty forbidden_imports")
    matching = next((pattern for pattern in patterns if _matches(import_name, pattern)), None)
    if matching:
        return matching
    return architecture_violation(path, import_name) if policy.get("enforce_phase_boundaries", True) else None
