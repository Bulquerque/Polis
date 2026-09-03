from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.models import (
    S5OutputBundle,
    S5RunRequest,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    S5QualificationReference,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import (
    RobustnessStressBundleManifest,
    S6OutputBundle,
    S6RunRequest,
)


class StrictModel(BaseModel):
    """Strict, immutable and closed integration model."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class RobustnessStressRunRequest(StrictModel):
    """Combined request for P9.S5 followed by P9.S6."""

    s5: S5RunRequest
    s6: S6RunRequest

    @model_validator(mode="after")
    def validate_shared_context(self) -> Self:
        s5_context = self.s5.dependence.context.model_dump(mode="json")
        s6_context = self.s6.scenario_registry.context.model_dump(mode="json")
        if s5_context != s6_context:
            raise ValueError("S5 and S6 must share the exact same RunContext")
        return self


class RobustnessStressOutputBundle(StrictModel):
    """Atomic output containing both subphases and their joint manifest."""

    bundle_id: str = Field(min_length=1, pattern=r".*\S.*")
    s5: S5OutputBundle
    s5_reference: S5QualificationReference
    s6: S6OutputBundle
    manifest: RobustnessStressBundleManifest
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_consistency(self) -> Self:
        if self.s5.context.model_dump(mode="json") != self.s6.context.model_dump(mode="json"):
            raise ValueError("S5 and S6 output contexts differ")
        if self.s5_reference.bundle_id != self.s5.bundle_id:
            raise ValueError("S5 reference does not identify the actual S5 bundle")
        if self.s5_reference.bundle_sha256 != self.s5.bundle_sha256:
            raise ValueError("S5 reference does not hash the actual S5 bundle")
        if self.manifest.s5_bundle_sha256 != self.s5.bundle_sha256:
            raise ValueError("manifest does not reference the actual S5 bundle")
        if self.manifest.s6_bundle_sha256 != self.s6.bundle_sha256:
            raise ValueError("manifest does not reference the actual S6 bundle")
        expected = content_sha256(
            {
                "s5_bundle_sha256": self.s5.bundle_sha256,
                "s6_bundle_sha256": self.s6.bundle_sha256,
                "manifest_sha256": self.manifest.manifest_sha256,
            }
        )
        if expected != self.bundle_sha256:
            raise ValueError("combined robustness-stress bundle hash mismatch")
        return self
