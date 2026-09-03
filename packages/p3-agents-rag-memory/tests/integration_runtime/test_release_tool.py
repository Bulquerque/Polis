"""Regression tests for the integrated release packager."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_release_module():
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / "tools" / "release.py"
    spec = importlib.util.spec_from_file_location("p3_release_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_tool_imports_and_validates() -> None:
    module = _load_release_module()
    errors = module.validate_release(module.PROJECT_ROOT, strict_hygiene=False)
    errors.extend(module._validate_markdown_links())
    errors.extend(module._validate_asset_mirrors())
    assert errors == []
