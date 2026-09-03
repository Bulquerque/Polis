"""Canonical module-to-contract acceptance gate for the current P3 snapshot."""

from __future__ import annotations

from functools import lru_cache
import asyncio
import importlib
import inspect
import sys
from pathlib import Path

import pytest
import yaml


PACKAGE = Path(__file__).resolve().parents[2]
ROOT = PACKAGE.parents[1]
MODULES = PACKAGE / "modules"
MATRIX_PATH = PACKAGE / "contracts" / "MODULE_IO_MATRIX.yaml"
STATUS_ROOT = ROOT / "phases" / "phase_03_agents_rag_memory" / "modules"


@lru_cache(maxsize=1)
def _matrix() -> dict[str, dict]:
    payload = yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8")) or {}
    rows = payload.get("module_io_matrix", [])
    return {str(row["module_id"]): row for row in rows}


@lru_cache(maxsize=1)
def _contracts() -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for row in _matrix().values():
        relative = str(row.get("module_contract") or "")
        path = PACKAGE / relative
        if path.is_file():
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            result.setdefault(str(payload.get("module_id") or ""), []).append(path)
    return result


@lru_cache(maxsize=1)
def _test_files() -> list[Path]:
    return sorted((PACKAGE / "tests").rglob("test_*.py"))


@pytest.mark.parametrize(
    "module_id",
    sorted(
        str(yaml.safe_load(path.read_text(encoding="utf-8")).get("module_id"))
        for path in MODULES.glob("P3_*.yaml")
    ),
)
def test_module_semantic_acceptance(module_id: str) -> None:
    matrix = _matrix()
    contracts = _contracts()
    assert module_id in matrix, f"module missing from MODULE_IO_MATRIX: {module_id}"
    selected = contracts.get(module_id, [])
    assert len(selected) == 1, f"expected one active contract for {module_id}: {selected}"

    contract_path = selected[0]
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    row = matrix[module_id]
    assert contract.get("module_id") == module_id
    assert contract.get("subphase") == row.get("subphase")
    assert contract.get("module_name") == row.get("module_name")
    assert row.get("module_contract") == contract_path.relative_to(PACKAGE).as_posix()
    assert contract.get("inputs") == row.get("consumes_from", {}).get("artifacts", [])
    assert contract.get("outputs") == row.get("emits_to", {}).get("artifacts", [])
    assert contract.get("tests_required"), f"tests_required is empty: {module_id}"

    source_path = (
        PACKAGE
        / "src"
        / "quant_pipeline"
        / "phase_03_agents_rag_memory"
        / "modules"
        / f"{contract_path.stem}.py"
    )
    assert source_path.is_file(), f"source missing for {module_id}: {source_path}"

    status_path = STATUS_ROOT / module_id / "module_requirement_status.json"
    assert status_path.is_file(), f"status missing for {module_id}: {status_path}"
    status = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}
    assert status.get("module_id") == module_id
    assert status.get("status") in {"pass", "PASS", "implemented", "implemented_qualified_internal"}

    assert any(path.name == "test_module_contracts.py" for path in _test_files())


def test_p3_semantic_acceptance_has_one_to_one_inventory() -> None:
    assert len(_matrix()) == 81
    assert len(_contracts()) == 81


P3_MODULE_IDS = sorted(_contracts())


@pytest.mark.parametrize("module_id", P3_MODULE_IDS, ids=lambda value: value.replace(".", "_"))
def test_module_strict_negative_domain_oracle(module_id: str) -> None:
    """Every P3 wrapper must reject an invocation without its declared inputs."""
    assert module_id in _matrix()
    contract_path = _contracts()[module_id][0]
    module_name = f"quant_pipeline.phase_03_agents_rag_memory.modules.{contract_path.stem}"
    source_root = str(PACKAGE / "src")
    sys.path.insert(0, source_root)
    try:
        module = importlib.import_module(module_name)
        with pytest.raises(Exception):
            result = module.run_module({}, {})
            if inspect.isawaitable(result):
                asyncio.run(result)
    finally:
        sys.path.remove(source_root)
