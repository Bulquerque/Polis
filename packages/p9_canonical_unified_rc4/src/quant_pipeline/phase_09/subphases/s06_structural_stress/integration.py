from __future__ import annotations

import json
from collections.abc import Mapping

from .contracts import S5QualificationReference


class S5CompatibilityError(ValueError):
    """Raised when an S5 bundle cannot be summarized safely."""


def summarize_s5_output_json(payload: str) -> S5QualificationReference:
    """Extract the immutable S5 qualification boundary from an S5 output bundle JSON."""

    raw = json.loads(payload)
    if not isinstance(raw, Mapping):
        raise S5CompatibilityError("S5 bundle must be a JSON object")
    bundle_id = raw.get("bundle_id")
    bundle_sha256 = raw.get("bundle_sha256")
    qualification = raw.get("qualification")
    if not isinstance(bundle_id, str) or not isinstance(bundle_sha256, str):
        raise S5CompatibilityError("S5 bundle identity fields are missing")
    if not isinstance(qualification, Mapping):
        raise S5CompatibilityError("S5 qualification object is missing")
    status = qualification.get("status")
    if not isinstance(status, str):
        raise S5CompatibilityError("S5 qualification status is missing")
    return S5QualificationReference(
        bundle_id=bundle_id,
        bundle_sha256=bundle_sha256,
        qualification_status=status,
    )
