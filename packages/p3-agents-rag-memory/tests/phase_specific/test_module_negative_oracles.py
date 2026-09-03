from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from pathlib import Path

import pytest
import yaml


PACKAGE = Path(__file__).resolve().parents[2]
MODULE_IDS = sorted(
    str((yaml.safe_load(path.read_text(encoding="utf-8")) or {})["module_id"])
    for path in (PACKAGE / "modules").glob("P3_*.yaml")
)


@pytest.mark.parametrize("module_id", MODULE_IDS, ids=lambda value: value.replace(".", "_"))
def test_module_strict_negative_domain_oracle(module_id: str) -> None:
    assert module_id in MODULE_IDS
    contract = next(
        path for path in (PACKAGE / "contracts" / "modules").glob(f"{module_id.replace('.', '_')}_*.yaml")
    )
    source_root = str(PACKAGE / "src")
    sys.path.insert(0, source_root)
    try:
        module = importlib.import_module(
            f"quant_pipeline.phase_03_agents_rag_memory.modules.{contract.stem}"
        )
        with pytest.raises(Exception):
            result = module.run_module({}, {})
            if inspect.isawaitable(result):
                asyncio.run(result)
            else:
                raise AssertionError("module accepted an empty declared-input set")
    finally:
        sys.path.remove(source_root)
