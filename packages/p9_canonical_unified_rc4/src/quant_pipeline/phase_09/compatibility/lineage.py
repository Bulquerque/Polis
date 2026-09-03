from __future__ import annotations

from datetime import datetime

from pydantic import model_validator

from quant_pipeline.phase_09.contracts.base import StrictModel

from .models import PhaseLineageFingerprint


class CrossPhaseLineageRegistry(StrictModel):
    registry_version: str
    phases: tuple[PhaseLineageFingerprint, ...]

    @model_validator(mode="after")
    def validate_phase_coverage(self) -> "CrossPhaseLineageRegistry":
        ids = [item.phase_id for item in self.phases]
        expected = {f"P{index}" for index in range(9)}
        if set(ids) != expected or len(ids) != len(set(ids)):
            raise ValueError("cross-phase registry must cover P0 through P8 exactly once")
        return self

    def resolve(self, phase_id: str) -> PhaseLineageFingerprint | None:
        return next((item for item in self.phases if item.phase_id == phase_id), None)
