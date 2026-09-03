"""External compatibility boundary for P0–P8.

The scientific subphases remain independent from historical or phase-specific wire
formats.  All cross-phase translation is explicit, typed and fail-closed here.
"""
from .facade import P9CompatibilityFacade
from .fingerprints import verify_phase_package_fingerprint
from .p0_consumer import validate_p0_control_plane_consumer
from .models import CompatibilityReceipt, CompatibilityState, SupplementalArtifact
from .p8_ingress import P8NativePublication, publish_p8_native_handoff

__all__ = [
    "CompatibilityReceipt",
    "CompatibilityState",
    "P8NativePublication",
    "P9CompatibilityFacade",
    "SupplementalArtifact",
    "publish_p8_native_handoff",
    "verify_phase_package_fingerprint",
    "validate_p0_control_plane_consumer",
]

from .modern_feedback import (
    ModernFeedbackMaterialization, P0FeedbackAuthorization,
    materialize_modern_p5_feedback, materialize_modern_p7_feedback,
)
