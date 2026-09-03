from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from quant_pipeline.phase_05_underlying_forecasts.registry import list_modules

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_all_45_entrypoints_import():
    modules = list_modules()
    assert len(modules) == 45
    assert len({module.subphase_id for module in modules}) == 9
    for module in modules:
        filename = f"{module.module_id.replace('.', '_')}_{module.name}"
        importlib.import_module(f"quant_pipeline.phase_05_underlying_forecasts.modules.{filename}")


def test_cli_is_portable_in_clean_subprocess(tmp_path):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SRC)
    completed = subprocess.run(
        [sys.executable, "-m", "quant_pipeline.phase_05_underlying_forecasts.cli", "doctor"],
        cwd=tmp_path,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert payload["module_count"] == 45
    assert payload["subphase_count"] == 9


def test_public_source_respects_code_limits_and_names():
    forbidden_names = {"utils.py", "helpers.py", "misc.py", "common.py"}
    package = SRC / "quant_pipeline/phase_05_underlying_forecasts"
    for path in package.rglob("*.py"):
        assert path.name not in forbidden_names
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 350, path
        tree = ast.parse("\n".join(lines))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert (node.end_lineno or node.lineno) - node.lineno + 1 <= 60, (path, node.name)
            if isinstance(node, ast.ClassDef):
                assert (node.end_lineno or node.lineno) - node.lineno + 1 <= 180, (path, node.name)


def test_no_legacy_engine_or_absolute_environment_paths():
    forbidden_parts = {"_engines", "bridges", "build"}
    package = SRC / "quant_pipeline/phase_05_underlying_forecasts"
    assert not any(forbidden_parts.intersection(path.parts) for path in package.rglob("*"))
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".toml"}:
            assert "/mnt" + "/data/" not in path.read_text(encoding="utf-8", errors="ignore")
