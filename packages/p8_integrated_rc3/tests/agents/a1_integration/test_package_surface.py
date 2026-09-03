from __future__ import annotations

from pathlib import Path


def test_namespace_package_is_not_shadowed() -> None:
    root = Path(__file__).parents[1]
    assert not (root / "src/quant_pipeline/__init__.py").exists()


def test_integration_package_has_no_duplicate_phase_contracts() -> None:
    root = Path(__file__).parents[1]
    assert not (root / "src/quant_pipeline/phase_08_contracts").exists()
