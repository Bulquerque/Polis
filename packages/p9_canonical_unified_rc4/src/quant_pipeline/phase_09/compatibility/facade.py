from __future__ import annotations

from .p0_reporting import build_p0_control_plane_reports
from .p0_consumer import validate_p0_control_plane_consumer
from .fingerprints import verify_phase_package_fingerprint
from .p3_boundary import (
    build_p3_belief_feedback,
    build_p3_retro_context_package,
    validate_p3_evaluation_boundary,
    validate_p3_belief_feedback_consumer,
    validate_p3_retro_context_consumer,
)
from .legacy_consumers import validate_legacy_feedback_consumer
from .p8_feedback import materialize_p8_promoted_feedback
from .p8_ingress import publish_p8_native_handoff


class P9CompatibilityFacade:
    """Stable public facade; internal scientific modules never import other phases."""

    publish_p8_native_handoff = staticmethod(publish_p8_native_handoff)
    validate_p3_evaluation_boundary = staticmethod(validate_p3_evaluation_boundary)
    validate_p3_belief_feedback_consumer = staticmethod(validate_p3_belief_feedback_consumer)
    validate_p3_retro_context_consumer = staticmethod(validate_p3_retro_context_consumer)
    build_p3_belief_feedback = staticmethod(build_p3_belief_feedback)
    build_p3_retro_context_package = staticmethod(build_p3_retro_context_package)
    materialize_p8_promoted_feedback = staticmethod(materialize_p8_promoted_feedback)
    validate_legacy_feedback_consumer = staticmethod(validate_legacy_feedback_consumer)
    build_p0_control_plane_reports = staticmethod(build_p0_control_plane_reports)
    validate_p0_control_plane_consumer = staticmethod(validate_p0_control_plane_consumer)
    verify_phase_package_fingerprint = staticmethod(verify_phase_package_fingerprint)
