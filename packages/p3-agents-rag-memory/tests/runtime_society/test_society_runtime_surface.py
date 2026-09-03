"""Integration tests for the consolidated society runtime surface."""
from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.society_runtime import validate_society_runtime


ROOT = Path(__file__).resolve().parents[2]


def test_consolidated_runtime_surface_is_valid() -> None:
    result = validate_society_runtime(ROOT)
    assert result["status"] == "PASS"
    assert result["errors"] == []
    assert result["module_count"] == 12
    assert result["production_promotion_allowed"] is False


def test_all_four_runtime_namespaces_exist() -> None:
    runtime_root = ROOT / "src" / "quant_pipeline" / "phase_03_agents_rag_memory"
    assert all((runtime_root / name).is_dir() for name in ("s25", "s26", "s27", "s28", "society_runtime"))
