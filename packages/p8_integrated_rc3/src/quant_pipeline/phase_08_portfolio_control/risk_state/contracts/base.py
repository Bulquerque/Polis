"""Shared strict contract base and upstream S3 contract imports."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ActionabilityState,
    ArtifactRef,
    ModuleReceipt,
    S3Result,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


__all__ = [
    "ActionabilityState", "ArtifactRef", "ModuleReceipt", "S3Result", "StrictModel",
]
