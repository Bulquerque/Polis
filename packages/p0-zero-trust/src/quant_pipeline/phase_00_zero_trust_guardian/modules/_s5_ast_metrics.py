from __future__ import annotations

import ast
from typing import Any

from ._module_executor import ContractValidationError


def parse_python(entry: dict[str, Any]) -> ast.Module | None:
    if not entry["path"].endswith(".py"):
        return None
    try:
        return ast.parse(entry["content"], filename=entry["path"])
    except SyntaxError as exc:
        raise ContractValidationError(f"invalid Python source {entry['path']}: {exc.msg}") from exc


def node_lines(node: ast.AST) -> int:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return max(1, end - start + 1)


def cyclomatic_complexity(node: ast.AST) -> int:
    score = 1
    branch_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Match)
    for child in ast.walk(node):
        if isinstance(child, branch_types):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
    return score


def public_function_count(tree: ast.Module) -> int:
    return sum(
        1 for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    )


def infer_phase_from_path(path: str) -> str | None:
    lowered = path.lower().replace("\\", "/")
    for number in range(10):
        tokens = (f"phase_{number:02d}_", f"/p{number}/", f"p{number}_", f"p{number}.")
        if any(token in lowered for token in tokens):
            return f"P{number}"
    return None
