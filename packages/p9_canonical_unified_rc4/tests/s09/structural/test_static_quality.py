from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src/quant_pipeline/phase_09/subphases/s09_competition_promotion"
EXPECTED_MODULE_IDS = {f"P9.S9.M{index:02d}" for index in range(1, 8)}
REASON_CODE_PATTERN = re.compile(r'"(P9_[A-Z0-9_]+)"')


def _python_files() -> tuple[Path, ...]:
    return tuple(sorted(SRC.rglob("*.py")))


def test_all_python_sources_parse() -> None:
    for path in _python_files():
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_typing_any_datetime_now_or_broad_exception_handler() -> None:
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                if any(alias.name == "Any" for alias in node.names):
                    violations.append(f"{path}: typing.Any")
            if isinstance(node, ast.Attribute) and node.attr == "now":
                if isinstance(node.value, ast.Name) and node.value.id == "datetime":
                    violations.append(f"{path}: datetime.now")
            if isinstance(node, ast.ExceptHandler):
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    violations.append(f"{path}: except Exception")
    assert not violations, violations


def test_source_lines_respect_100_character_limit() -> None:
    violations: list[str] = []
    for path in _python_files():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if len(line) > 100:
                violations.append(f"{path}:{line_number}:{len(line)}")
    assert not violations, violations


def test_module_registry_has_exact_s9_ownership() -> None:
    registry = json.loads(
        (ROOT / "registries/s09/module_registry.json").read_text(encoding="utf-8")
    )
    module_ids = {entry["module_id"] for entry in registry["modules"]}
    assert module_ids == EXPECTED_MODULE_IDS
    assert len(registry["modules"]) == 7


def test_source_reason_codes_are_registered() -> None:
    registry = json.loads(
        (ROOT / "registries/s09/reason_code_registry.json").read_text(encoding="utf-8")
    )
    registered = set(registry["reason_codes"])
    used: set[str] = set()
    for path in _python_files():
        used.update(REASON_CODE_PATTERN.findall(path.read_text(encoding="utf-8")))
    assert used <= registered, sorted(used - registered)


def test_all_yaml_documents_parse() -> None:
    yaml_files = sorted((ROOT / "schemas" / "s09").glob("*.yaml")) + sorted(
        (ROOT / "registries" / "s09").glob("*.yaml")
    )
    assert yaml_files
    for path in yaml_files:
        yaml.safe_load(path.read_text(encoding="utf-8"))
