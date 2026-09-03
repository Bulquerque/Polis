from __future__ import annotations

from quant_pipeline.phase_09.subphases.s05_bootstrap_inference.runner import run_s5
from quant_pipeline.phase_09.subphases.s06_structural_stress.contracts import (
    S5QualificationReference,
    content_sha256,
)
from quant_pipeline.phase_09.subphases.s06_structural_stress.runner import (
    build_robustness_stress_manifest,
    run_s6,
)

from .contracts import RobustnessStressOutputBundle, RobustnessStressRunRequest


class RobustnessStressIntegrationError(RuntimeError):
    """Raised when S5 and S6 cannot be integrated without semantic drift."""


def run_robustness_stress(request: RobustnessStressRunRequest) -> RobustnessStressOutputBundle:
    """Run S5 then S6, binding S6 to the actual immutable S5 output."""

    s5_bundle = run_s5(request.s5)
    s5_reference = S5QualificationReference(
        bundle_id=s5_bundle.bundle_id,
        bundle_sha256=s5_bundle.bundle_sha256,
        qualification_status=s5_bundle.qualification.status.value,
    )
    scenario_registry = request.s6.scenario_registry.model_copy(
        update={"s5_qualification": s5_reference}
    )
    s6_request = request.s6.model_copy(update={"scenario_registry": scenario_registry})
    if s5_bundle.context.model_dump(mode="json") != scenario_registry.context.model_dump(
        mode="json"
    ):
        raise RobustnessStressIntegrationError("S5 output and S6 request contexts diverged")

    s6_bundle = run_s6(s6_request)
    manifest = build_robustness_stress_manifest(
        s5_bundle.bundle_sha256,
        s5_bundle.qualification.status.value,
        s6_bundle,
    )
    payload = {
        "s5_bundle_sha256": s5_bundle.bundle_sha256,
        "s6_bundle_sha256": s6_bundle.bundle_sha256,
        "manifest_sha256": manifest.manifest_sha256,
    }
    digest = content_sha256(payload)
    return RobustnessStressOutputBundle(
        bundle_id=f"{s5_bundle.context.run_id}:P9.S5S6:{digest[:16]}",
        s5=s5_bundle,
        s5_reference=s5_reference,
        s6=s6_bundle,
        manifest=manifest,
        bundle_sha256=digest,
    )
