"""Resolve canonical runtime assets in source and installed environments."""

from __future__ import annotations

from pathlib import Path


def packaged_asset_root() -> Path:
    """Return assets distributed inside the installable Python package."""

    return Path(__file__).resolve().parents[1] / "assets"


def source_or_packaged_root() -> Path:
    """Prefer source-release authorities and fall back to packaged mirrors."""

    source_root = Path(__file__).resolve().parents[5]
    if (source_root / "schemas").is_dir() and (source_root / "config").is_dir():
        return source_root
    return packaged_asset_root()
