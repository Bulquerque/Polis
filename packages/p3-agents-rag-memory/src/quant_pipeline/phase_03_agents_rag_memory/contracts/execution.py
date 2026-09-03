"""Canonical execution contracts shared by all P3 modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from .base import RunIdentity


class ExecutionProfile(StrEnum):
    """Controls whether reference adapters or external providers may be used."""

    TEST = "TEST"
    REPLAY = "REPLAY"
    LIVE = "LIVE"


@dataclass(frozen=True, slots=True)
class ModuleExecutionContext:
    """Dependency-injected execution context used by every public module entrypoint.

    The context is intentionally a dataclass rather than a serialized contract:
    services such as clocks, stores and provider ports are process-local objects.
    Configuration is copied into immutable mapping proxies to prevent a module
    from mutating another module's run configuration.
    """

    profile: ExecutionProfile = ExecutionProfile.TEST
    run_identity: RunIdentity | None = None
    cycle_id: str | None = None
    config: Mapping[str, Any] = field(default_factory=dict)
    services: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
        object.__setattr__(self, "services", MappingProxyType(dict(self.services)))

    def legacy_config(self) -> dict[str, Any]:
        """Build the temporary compatibility mapping for legacy internal wrappers."""

        merged = dict(self.config)
        for name, service in self.services.items():
            merged.setdefault(name, service)
        merged.setdefault("execution_profile", self.profile.value)
        if self.run_identity is not None:
            merged.setdefault("run_identity", self.run_identity)
        if self.cycle_id is not None:
            merged.setdefault("cycle_id", self.cycle_id)
        return merged


class CanonicalModuleEntrypoint(Protocol):
    """The only supported public entrypoint shape for a P3 module."""

    async def __call__(
        self,
        inputs: Mapping[str, Any],
        context: ModuleExecutionContext,
    ) -> Mapping[str, Any]: ...
