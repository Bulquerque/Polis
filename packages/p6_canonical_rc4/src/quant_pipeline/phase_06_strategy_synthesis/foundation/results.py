"""Stable module and subphase result models."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .artifacts import FrozenModel


class Diagnostic(FrozenModel):
    reason_code: str
    severity: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ModuleResult(FrozenModel):
    module_id: str
    outputs: dict[str, Any]
    diagnostics: tuple[Diagnostic, ...] = ()


class SubphaseResult(FrozenModel):
    subphase_id: str
    module_results: tuple[ModuleResult, ...]
    outputs: dict[str, Any]
    capability_status: str = "AVAILABLE"
