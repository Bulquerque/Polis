from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/quant_pipeline/phase_09/subphases/s10_memory_release"


def test_namespace_roots_are_implicit() -> None:
    assert not (ROOT / "src/quant_pipeline/__init__.py").exists()
    assert not (ROOT / "src/quant_pipeline/phase_09/__init__.py").exists()
    assert not (ROOT / "src/quant_pipeline/phase_09/subphases/__init__.py").exists()


def test_domain_has_no_any_global_clock_or_generic_exception() -> None:
    violations = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                if any(alias.name == "Any" for alias in node.names):
                    violations.append(f"{path}: Any")
            if isinstance(node, ast.Attribute) and node.attr == "now":
                if isinstance(node.value, ast.Name) and node.value.id == "datetime":
                    violations.append(f"{path}: datetime.now")
            if isinstance(node, ast.ExceptHandler):
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    violations.append(f"{path}: except Exception")
    assert not violations


def test_python_lines_fit_standard() -> None:
    violations = []
    for path in tuple(SRC.rglob("*.py")) + tuple((ROOT / "tests" / "s10").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if len(line) > 100:
                violations.append(f"{path}:{number}:{len(line)}")
    assert not violations
