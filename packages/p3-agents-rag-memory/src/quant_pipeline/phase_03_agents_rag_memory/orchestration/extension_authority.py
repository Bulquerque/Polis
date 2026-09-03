"""Packaged authority for the optional P3 research-tools extension (S32-S40).

The extension is intentionally additive: the original 81-module registry remains
available as ``LEGACY_MODULE_REGISTRY`` while the public runtime can discover all
128 logical P3 modules through one canonical facade.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

_EXTENSION_ROOT = "config/research_tools"


@lru_cache(maxsize=1)
def extension_module_rows() -> tuple[Mapping[str, Any], ...]:
    root = files("quant_pipeline.phase_03_agents_rag_memory.assets")
    document = yaml.safe_load(
        root.joinpath(_EXTENSION_ROOT, "MODULE_REGISTRY_S32_S40.yaml").read_text(encoding="utf-8")
    )
    rows = tuple(dict(item) for item in document.get("modules", ()))
    if len(rows) != 47:
        raise RuntimeError(f"research-tools registry contains {len(rows)} modules; expected 47")
    ids = {str(item.get("module_id")) for item in rows}
    if len(ids) != 47:
        raise RuntimeError("research-tools registry contains duplicate module IDs")
    return rows


@lru_cache(maxsize=1)
def extension_io_rows() -> tuple[Mapping[str, Any], ...]:
    root = files("quant_pipeline.phase_03_agents_rag_memory.assets")
    document = yaml.safe_load(
        root.joinpath(_EXTENSION_ROOT, "MODULE_IO_MATRIX_S32_S40.yaml").read_text(encoding="utf-8")
    )
    rows = tuple(dict(item) for item in document.get("records", ()))
    if len(rows) != 47:
        raise RuntimeError(f"research-tools IO matrix contains {len(rows)} modules; expected 47")
    ids = {str(item.get("module_id")) for item in rows}
    if len(ids) != 47:
        raise RuntimeError("research-tools IO matrix contains duplicate module IDs")
    return rows


__all__ = ["extension_module_rows", "extension_io_rows"]
