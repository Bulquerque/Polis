"""Temporary compatibility metadata for pre-P3-FINAL entrypoints."""
from __future__ import annotations

import functools
import inspect
import os
import warnings
from collections.abc import Callable
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


class P3LegacyEntrypointWarning(DeprecationWarning):
    """A caller used run_module/run_module_async instead of execute."""


def deprecated_legacy_entrypoint(module_id: str) -> Callable[[F], F]:
    """Mark a legacy wrapper deprecated and optionally emit a warning.

    Warnings are opt-in via ``P3_EMIT_LEGACY_DEPRECATION_WARNINGS=1`` so the
    compatibility test suite remains readable during the removal window.
    """

    def decorate(function: F) -> F:
        message = f"{module_id}.{function.__name__} is deprecated; use async execute(inputs, context)"
        emit = os.getenv("P3_EMIT_LEGACY_DEPRECATION_WARNINGS") == "1"
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if emit:
                    warnings.warn(message, P3LegacyEntrypointWarning, stacklevel=2)
                return await function(*args, **kwargs)
            wrapped = cast(F, async_wrapper)
        else:
            @functools.wraps(function)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if emit:
                    warnings.warn(message, P3LegacyEntrypointWarning, stacklevel=2)
                return function(*args, **kwargs)
            wrapped = cast(F, wrapper)
        setattr(wrapped, "__p3_deprecated__", True)
        setattr(wrapped, "__p3_replacement__", "execute")
        return wrapped
    return decorate


__all__ = ["P3LegacyEntrypointWarning", "deprecated_legacy_entrypoint"]
