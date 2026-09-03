"""Explicit process-local object store for non-serializable research-tool runtime objects."""
from __future__ import annotations

from threading import RLock
from typing import Any


class ProcessLocalRuntimeStore:
    """Thread-safe, dependency-injected store scoped to one composition root.

    Callables, ports and gateway objects never enter the serialized artifact DAG.
    The store is passed through ``ModuleExecutionContext.services`` and therefore
    is neither hidden global state nor persisted across runs.
    """

    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}
        self._lock = RLock()

    def put(self, key: str, value: Any, *, replace: bool = False) -> None:
        with self._lock:
            if not replace and key in self._objects and self._objects[key] is not value:
                raise ValueError(f"runtime object key already exists: {key}")
            self._objects[key] = value

    def get(self, key: str) -> Any:
        with self._lock:
            try:
                return self._objects[key]
            except KeyError as exc:
                raise KeyError(f"runtime object not found: {key}") from exc

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._objects

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._objects))


def require_runtime_store(services: object) -> ProcessLocalRuntimeStore:
    if not isinstance(services, dict):
        try:
            value = services.get("research_tool_runtime_store")  # type: ignore[attr-defined]
        except AttributeError as exc:
            raise TypeError("services must expose a mapping-like get()") from exc
    else:
        value = services.get("research_tool_runtime_store")
    if not isinstance(value, ProcessLocalRuntimeStore):
        raise RuntimeError(
            "research_tool_runtime_store service is required for canonical S40 composition"
        )
    return value


__all__ = ["ProcessLocalRuntimeStore", "require_runtime_store"]
