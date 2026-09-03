from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_all_canonical_modules_import_without_optional_dependencies(root: Path) -> None:
    script = r'''
import importlib
import importlib.abc
import json
import sys

BLOCKED = {"httpx", "pyarrow", "neo4j", "mcp", "opentelemetry", "networkx"}

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in BLOCKED:
            raise ModuleNotFoundError(f"blocked optional dependency: {root}", name=root)
        return None

sys.meta_path.insert(0, BlockOptional())
from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import MODULE_REGISTRY
errors = []
for row in MODULE_REGISTRY:
    try:
        importlib.import_module(row.implementation_path)
    except Exception as exc:
        errors.append({"module_id": row.module_id, "error": type(exc).__name__, "message": str(exc)})
print(json.dumps({"count": len(MODULE_REGISTRY), "errors": errors}))
raise SystemExit(1 if errors else 0)
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result == {"count": 81, "errors": []}


def test_core_dependencies_do_not_include_optional_providers(root: Path) -> None:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    core_block = pyproject.split("[project.optional-dependencies]", 1)[0]
    for package in ("httpx", "networkx", "pyarrow", "neo4j", "mcp", "opentelemetry"):
        assert package not in core_block.lower()
