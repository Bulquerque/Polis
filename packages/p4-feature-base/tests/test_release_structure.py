from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PHASE = ROOT / "src" / "quant_pipeline" / "phase_04_feature_base"
LEGACY_COMPATIBILITY_ALIASES = {"P4_S1_M01_phase2_feature_intake_validator"}


def _canonical_module_files() -> list[Path]:
    return sorted(
        path
        for path in (PHASE / "modules").glob("P4_S*_M*.py")
        if path.stem not in LEGACY_COMPATIBILITY_ALIASES
    )


def test_all_49_module_wrappers_exist() -> None:
    module_files = _canonical_module_files()
    assert len(module_files) == 49
    assert all((PHASE / "modules" / alias).with_suffix(".py").is_file() for alias in LEGACY_COMPATIBILITY_ALIASES)


def test_legacy_alias_is_provenance_backed_and_not_canonical() -> None:
    authority = yaml.safe_load(
        (ROOT / "contracts" / "CONTRACT_AUTHORITY.yaml").read_text(encoding="utf-8")
    )
    aliases = authority["compatibility_aliases"]
    assert {item["alias_stem"] for item in aliases} == LEGACY_COMPATIBILITY_ALIASES
    catalog_ids = {
        row.split(",", 1)[0]
        for row in (ROOT / "MODULE_CATALOG.csv").read_text(encoding="utf-8").splitlines()[1:]
    }
    for item in aliases:
        assert item["module_id"] in catalog_ids
        assert item["alias_stem"] not in catalog_ids
        assert (ROOT / item["source_path"]).is_file()
        assert (ROOT / item["canonical_source_path"]).is_file()
        assert item["requirements_covered"]
        assert item["validation_result"] == "PASS"


def test_yaml_contracts_are_parseable() -> None:
    for directory in (ROOT / "contracts", ROOT / "schemas", ROOT / "registries"):
        for path in directory.rglob("*.yaml"):
            yaml.safe_load(path.read_text(encoding="utf-8"))


def test_productive_source_avoids_dynamic_execution() -> None:
    findings: list[str] = []
    forbidden_calls = {"eval", "exec", "compile", "os.system", "subprocess.run", "subprocess.Popen"}
    for path in PHASE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            else:
                continue
            if name in forbidden_calls:
                findings.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
    assert findings == []


def test_all_module_wrappers_import() -> None:
    import os
    import subprocess
    import sys

    names = [
        "quant_pipeline.phase_04_feature_base.modules." + path.stem
        for path in _canonical_module_files()
    ]
    code = (
        "import importlib, os, sys; "
        "sys.path[:] = [path for path in sys.path if 'phase_03_extracted' not in path]; "
        "import quant_pipeline; "
        f"quant_pipeline.__path__.append({str(ROOT / 'src' / 'quant_pipeline')!r}); "
        f"names={names!r}; "
        "assert all(callable(importlib.import_module(name).run_module) for name in names); "
        "print('WRAPPER_IMPORT_SMOKE: PASS', flush=True); os._exit(0)"
    )
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(ROOT / "src"), inherited_pythonpath) if path
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
