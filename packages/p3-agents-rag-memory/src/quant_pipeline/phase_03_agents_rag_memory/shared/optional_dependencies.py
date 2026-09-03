from __future__ import annotations

import importlib
from types import ModuleType


class OptionalDependencyUnavailableError(RuntimeError):
    """Raised when an explicitly requested adapter extra is not installed."""


def require_dependency(import_name: str, *, extra: str, purpose: str) -> ModuleType:
    """Import an optional dependency or raise a stable, actionable error."""
    try:
        return importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        if exc.name != import_name and not str(exc.name).startswith(f"{import_name}."):
            raise
        raise OptionalDependencyUnavailableError(
            f"Optional dependency '{import_name}' is required for {purpose}. "
            f"Install the project extra '[{extra}]'."
        ) from exc


def dependency_available(import_name: str) -> bool:
    """Return whether an optional dependency can be imported."""
    try:
        importlib.import_module(import_name)
    except ModuleNotFoundError:
        return False
    return True
