"""Small, explicit helpers shared by canonical module entrypoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from typing import Any, TypeVar

T = TypeVar("T")


def run_coroutine(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run an async module from synchronous orchestration.

    Async callers must use the module's ``run_module_async`` entrypoint instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    raise RuntimeError(
        "run_module cannot be called inside an active event loop; "
        "use run_module_async"
    )


def require_service(
    config: Mapping[str, Any] | None,
    *,
    expected_type: type[T],
) -> T:
    """Return the dependency-injected service or fail closed."""
    service = (config or {}).get("service")
    if not isinstance(service, expected_type):
        raise TypeError(f"config.service must be {expected_type.__name__}")
    return service
