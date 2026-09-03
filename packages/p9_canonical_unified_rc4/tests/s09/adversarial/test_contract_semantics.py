from __future__ import annotations

from datetime import timedelta, timezone

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s09_competition_promotion.models import (
    ArtifactReference,
    CycleRef,
    S9ExecutionEnvelope,
)

from tests.s09.conftest import H, NOW, artifact_ref


def test_artifact_reference_requires_true_utc() -> None:
    payload = artifact_ref().model_dump()
    payload["available_at"] = NOW.astimezone(timezone(timedelta(hours=3)))
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(payload)


def test_artifact_reference_rejects_whitespace_location() -> None:
    payload = artifact_ref().model_dump()
    payload["location"] = "   "
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(payload)


def test_execution_envelope_rejects_wrong_hash(valid_input_bundle) -> None:
    from quant_pipeline.phase_09.subphases.s09_competition_promotion.service import run_s9_subphase

    envelope = run_s9_subphase(inputs=valid_input_bundle, created_at=NOW)
    with pytest.raises(ValidationError):
        S9ExecutionEnvelope(payload=envelope.payload, payload_sha256="0" * 64)
