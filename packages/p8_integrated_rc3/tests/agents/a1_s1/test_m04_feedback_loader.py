from __future__ import annotations

from decimal import Decimal

import pytest

from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.p9 import (
    LiquidityHaircutFeedback,
    LiquidityHaircutPayload,
    P0PolicyAuthorizationV1,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import (
    InMemoryArtifactStore,
    InMemoryIdempotencyStore,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    FeedbackAuthorizationError,
    FeedbackOutOfBoundsError,
    HashMismatchError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m04_promoted_portfolio_feedback_loader import (
    run_module,
)

from tests.agents.a1_s1.factories import finalize_hash, full_fixture, make_feedback_artifacts, raw_ref


def test_empty_feedback_set_is_valid() -> None:
    fixture = full_fixture(ranked=False)
    result = run_module(
        (),
        store=fixture.artifact_store,
        idempotency_store=InMemoryIdempotencyStore(),
        context=fixture.request.context,
    )
    assert result.feedback_context.applied_feedback == ()


def test_authorized_feedback_is_applied_once() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    store = InMemoryIdempotencyStore()
    first = run_module(
        fixture.request.feedback_refs,
        store=fixture.artifact_store,
        idempotency_store=store,
        context=fixture.request.context,
    )
    second = run_module(
        fixture.request.feedback_refs,
        store=fixture.artifact_store,
        idempotency_store=store,
        context=fixture.request.context,
    )
    assert len(first.feedback_context.applied_feedback) == 1
    assert second.feedback_context.item_receipts[0].status.value == "ALREADY_APPLIED"


def test_feedback_target_cycle_must_match() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    ref = fixture.request.feedback_refs[0]
    feedback = LiquidityHaircutFeedback.model_validate_json(artifacts[ref.artifact_id], strict=True)
    altered = finalize_hash(feedback.model_copy(update={"target_cycle_id": "other-cycle", "content_sha256": "0" * 64}))
    raw = altered.model_dump_json().encode()
    altered_ref = raw_ref(
        "feedback-other-cycle",
        "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        raw,
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
    )
    artifacts[altered_ref.artifact_id] = raw
    with pytest.raises(FeedbackAuthorizationError, match="target cycle"):
        run_module(
            (altered_ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_feedback_above_p0_numeric_bound_is_rejected() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    feedback_ref = fixture.request.feedback_refs[0]
    feedback = LiquidityHaircutFeedback.model_validate_json(artifacts[feedback_ref.artifact_id], strict=True)
    altered_feedback = finalize_hash(
        feedback.model_copy(
            update={
                "payload": LiquidityHaircutPayload(
                    instrument_family="OPTION", haircut_ratio=Decimal("0.75")
                ),
                "content_sha256": "0" * 64,
            }
        )
    )
    raw = altered_feedback.model_dump_json().encode()
    altered_ref = raw_ref(
        "feedback-out-of-bounds",
        "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        raw,
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
    )
    artifacts[altered_ref.artifact_id] = raw
    with pytest.raises(FeedbackOutOfBoundsError):
        run_module(
            (altered_ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_feedback_hash_tampering_is_fatal() -> None:
    artifacts, ref = make_feedback_artifacts()
    artifacts[ref.artifact_id] = b"tampered"
    fixture = full_fixture(ranked=False)
    with pytest.raises(HashMismatchError):
        run_module(
            (ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )


def test_p0_authorization_must_match_feedback() -> None:
    fixture = full_fixture(ranked=False, include_feedback=True)
    artifacts = fixture.artifact_store.export()
    feedback_ref = fixture.request.feedback_refs[0]
    feedback = LiquidityHaircutFeedback.model_validate_json(artifacts[feedback_ref.artifact_id], strict=True)
    auth_ref = feedback.p0_authorization_ref
    auth = P0PolicyAuthorizationV1.model_validate_json(artifacts[auth_ref.artifact_id], strict=True)
    altered_auth = auth.model_copy(update={"feedback_id": "wrong-feedback"})
    altered_raw = altered_auth.model_dump_json().encode()
    altered_auth_ref = raw_ref("auth-wrong", "P0_POLICY_AUTHORIZATION_V1", altered_raw)
    artifacts[altered_auth_ref.artifact_id] = altered_raw
    altered_feedback = finalize_hash(
        feedback.model_copy(update={"p0_authorization_ref": altered_auth_ref, "content_sha256": "0" * 64})
    )
    altered_feedback_raw = altered_feedback.model_dump_json().encode()
    altered_feedback_ref = raw_ref(
        "feedback-wrong-auth",
        "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        altered_feedback_raw,
        contract_version="P9_TO_P8_PROMOTED_FEEDBACK_V1",
    )
    artifacts[altered_feedback_ref.artifact_id] = altered_feedback_raw
    with pytest.raises(FeedbackAuthorizationError):
        run_module(
            (altered_feedback_ref,),
            store=InMemoryArtifactStore(artifacts),
            idempotency_store=InMemoryIdempotencyStore(),
            context=fixture.request.context,
        )
