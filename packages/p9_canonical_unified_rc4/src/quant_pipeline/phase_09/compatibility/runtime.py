from __future__ import annotations

from importlib import import_module, metadata
from typing import Any

from .errors import PhaseUnavailableError


def import_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise PhaseUnavailableError(f"optional phase module is unavailable: {module_name}") from exc
    try:
        return getattr(module, symbol_name)
    except AttributeError as exc:
        raise PhaseUnavailableError(f"optional phase symbol is unavailable: {module_name}.{symbol_name}") from exc


def package_version(distribution_name: str, fallback: str = "source-tree") -> str:
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return fallback


def model_data(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="python", exclude_none=False)
    elif isinstance(value, dict):
        data = dict(value)
    else:
        raise TypeError("phase payload must be a Pydantic model or mapping")
    if not isinstance(data, dict):
        raise TypeError("phase payload must serialize to a mapping")
    return data
