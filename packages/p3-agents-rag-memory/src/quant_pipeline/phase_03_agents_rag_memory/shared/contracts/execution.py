"""Uniform execution envelope returned by the canonical module facade."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import StrictModel


class ModuleExecutionEnvelope(StrictModel):
    """Stable public result for any of the 81 P3 modules."""

    module_id: str = Field(pattern=r"^P3\.S\d+\.M\d+$")
    module_name: str = Field(min_length=1)
    subphase_id: str = Field(pattern=r"^P3\.S\d+$")
    implementation_status: Literal[
        "IMPLEMENTED_UNQUALIFIED",
        "IMPLEMENTED_QUALIFIED_INTERNAL",
    ] = "IMPLEMENTED_QUALIFIED_INTERNAL"
    production_promotion_allowed: Literal[False] = False
    outputs: dict[str, object]
