from __future__ import annotations

import ast
from pathlib import Path


def test_productive_code_has_no_print_and_no_datetime_now() -> None:
    root = Path("src/quant_pipeline")
    violations: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                if path.name != "cli.py":
                    violations.append(f"print:{path}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"now", "utcnow"}:
                    violations.append(f"wall-clock:{path}:{node.lineno}")
    assert not violations


def test_no_generic_executor_or_ambiguous_utility_module() -> None:
    names = {path.name for path in Path("src").rglob("*.py")}
    assert "_module_executor.py" not in names
    assert "utils.py" not in names
    assert "helpers.py" not in names
    assert "misc.py" not in names
