from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/quant_pipeline/phase_09"
EXTERNAL_PHASE = re.compile(r"^quant_pipeline\.phase_0[0-8](?:[_.]|$)")


def _cross_phase_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names if EXTERNAL_PHASE.match(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if EXTERNAL_PHASE.match(node.module):
                found.append(node.module)
    return found


def test_scientific_modules_do_not_import_other_phase_runtimes() -> None:
    violations: dict[str, list[str]] = {}
    for path in SOURCE.rglob("*.py"):
        if "compatibility" in path.parts:
            continue
        imports = _cross_phase_imports(path)
        if imports:
            violations[str(path.relative_to(ROOT))] = imports
    assert violations == {}


def test_compatibility_package_contains_no_static_cross_phase_imports() -> None:
    # P3 snippets are process-isolated strings; runtime discovery is intentionally dynamic.
    violations: dict[str, list[str]] = {}
    for path in (SOURCE / "compatibility").rglob("*.py"):
        imports = _cross_phase_imports(path)
        if imports:
            violations[str(path.relative_to(ROOT))] = imports
    assert violations == {}
