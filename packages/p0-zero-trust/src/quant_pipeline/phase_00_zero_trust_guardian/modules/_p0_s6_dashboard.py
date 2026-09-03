"""Backward-compatible P0.S6 helper facade.

The implementation was split into focused modules during the P0.S6 reform.
Existing private imports continue to resolve through this facade while new code
should import from _p0_s6_core, _p0_s6_state, or _p0_s6_render directly.
"""

from __future__ import annotations

from ._p0_s6_core import (
    digest,
    envelope,
    materialized,
    require_config,
    require_inputs,
    result,
    s6_control as control,
    source_summary as summary,
    validate,
)

__all__ = [
    "control",
    "digest",
    "envelope",
    "materialized",
    "require_config",
    "require_inputs",
    "result",
    "summary",
    "validate",
]
