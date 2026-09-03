from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_namespace_roots_are_implicit() -> None:
    assert not (ROOT / "src/quant_pipeline/__init__.py").exists()
    assert not (ROOT / "src/quant_pipeline/phase_09/__init__.py").exists()
    assert not (ROOT / "src/quant_pipeline/phase_09/subphases/__init__.py").exists()


def test_no_cache_or_bytecode_in_source_tree() -> None:
    assert not list(ROOT.rglob("__pycache__"))
    assert not list(ROOT.rglob("*.pyc"))
