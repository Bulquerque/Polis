from __future__ import annotations

from quant_pipeline.phase_09.contracts.artifacts import ArtifactAbsenceState, ArtifactSlot
from quant_pipeline.phase_09.contracts.handoff import P8EvaluationHandoffPayload, P8EvaluationHandoffV1
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.validation import HandoffValidationStatus
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import (
    P8EvaluationHandoffValidator,
)


def _validator(fixture):
    return P8EvaluationHandoffValidator(
        compatibility=fixture.compatibility,
        module_registry=fixture.module_registry,
        schema_registry=fixture.schema_registry,
        artifact_store=fixture.store,
    )


def test_full_handoff_is_accepted(full_fixture) -> None:
    outcome = _validator(full_fixture).validate(full_fixture.handoff)
    assert outcome.validated is not None
    assert outcome.report.status is HandoffValidationStatus.ACCEPTED_FULL
    assert len(outcome.validated.accepted_artifacts) == len(full_fixture.handoff.payload.artifacts)


def test_tampered_handoff_hash_is_rejected(full_fixture) -> None:
    tampered = full_fixture.handoff.model_copy(
        update={"integrity": IntegrityEnvelope(payload_sha256="1" * 64)}
    )
    outcome = _validator(full_fixture).validate(tampered)
    assert outcome.validated is None
    assert outcome.report.status is HandoffValidationStatus.REJECTED_INTEGRITY


def test_missing_required_artifact_is_rejected(full_fixture) -> None:
    slots = list(full_fixture.handoff.payload.artifacts)
    original = slots[0]
    slots[0] = ArtifactSlot(
        role=original.role,
        absence_state=ArtifactAbsenceState.NOT_PRODUCED,
        reason_codes=("P9_S1_HANDOFF_REQUIRED_ARTIFACT_MISSING",),
    )
    payload = full_fixture.handoff.payload.model_copy(update={"artifacts": tuple(slots)})
    handoff = P8EvaluationHandoffV1(
        payload=P8EvaluationHandoffPayload.model_validate(payload),
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )
    outcome = _validator(full_fixture).validate(handoff)
    assert outcome.validated is None
    assert outcome.report.status is HandoffValidationStatus.REJECTED_INCOMPLETE


def test_artifact_content_tampering_is_rejected(full_fixture) -> None:
    reference = full_fixture.handoff.payload.artifacts[0].reference
    assert reference is not None
    full_fixture.store._objects[reference.location] = b"tampered"  # adversarial test adapter state
    outcome = _validator(full_fixture).validate(full_fixture.handoff)
    assert outcome.validated is None
    assert outcome.report.status is HandoffValidationStatus.REJECTED_INTEGRITY


def test_handoff_published_after_evaluation_as_of_is_rejected(full_fixture) -> None:
    outcome = _validator(full_fixture).validate(
        full_fixture.handoff,
        evaluation_as_of=full_fixture.handoff.payload.published_at - __import__("datetime").timedelta(seconds=1),
    )
    assert outcome.validated is None
    assert outcome.report.status is HandoffValidationStatus.REJECTED_INCOMPLETE
    assert any(check.check_id == "handoff_publication_time" and not check.passed for check in outcome.report.checks)
