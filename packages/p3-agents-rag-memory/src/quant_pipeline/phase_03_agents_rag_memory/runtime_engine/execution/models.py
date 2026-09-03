from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from pydantic import JsonValue

from ..contracts_internal import ArtifactPointer, RuntimeIssue

JsonPayload = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ModuleInvocation:
    """Internal, explicit invocation of one whitelisted P3 module."""

    inputs: Mapping[str, JsonValue]
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    runtime: object | None = None


@dataclass(frozen=True, slots=True)
class ModuleExecutionResult:
    outputs: Mapping[str, JsonPayload]
    issues: tuple[RuntimeIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactWriteRequest:
    artifact_name: str
    payload: JsonPayload
    producer_module_id: str
    schema_id: str
    schema_version: str = "1.0.0"
    lineage_id: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedModuleOutput:
    pointers: Mapping[str, ArtifactPointer]
    payloads: Mapping[str, JsonPayload]
