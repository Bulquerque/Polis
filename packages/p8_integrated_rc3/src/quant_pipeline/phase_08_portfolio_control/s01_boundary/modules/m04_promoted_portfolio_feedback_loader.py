"""P8.S1.M04 — load only typed, authorized, next-cycle feedback."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import FeedbackRecommendationStatus, ReceiptStatus
from pydantic import ValidationError

from quant_pipeline.phase_08_contracts.p9 import (
    PROMOTED_FEEDBACK_ADAPTER,
    AllowedValuesAuthorizationBound,
    NumericAuthorizationBound,
    P0PolicyAuthorizationV1,
    P9FeedbackRecommendationV1,
    PromotedFeedback,
)
from quant_pipeline.phase_08_contracts.s1 import (
    FeedbackItemReceipt,
    M04Result,
    PromotedPortfolioFeedbackContext,
)

from ..context import S1ExecutionContext
from ..errors import FeedbackAuthorizationError, FeedbackOutOfBoundsError, TemporalIntegrityError
from ..module_support import (
    build_receipt,
    load_json_object,
    read_verified_artifact,
    validate_model_json,
    verify_model_embedded_hash,
)
from ..ports import ArtifactStorePort, IdempotencyStorePort

MODULE_ID = "P8.S1.M04"


def _payload_mapping(feedback: PromotedFeedback) -> dict[str, object]:
    return feedback.payload.model_dump(mode="python")


def _iter_numeric_values(value: object) -> Iterable[Decimal]:
    if isinstance(value, Decimal):
        yield value
    elif isinstance(value, tuple):
        for item in value:
            yield from _iter_numeric_values(item)


def _validate_numeric_bound(payload: dict[str, object], bound: NumericAuthorizationBound) -> None:
    if bound.field_name not in payload:
        raise FeedbackAuthorizationError(f"authorized numeric field absent from payload: {bound.field_name}")
    values = tuple(_iter_numeric_values(payload[bound.field_name]))
    if not values:
        raise FeedbackAuthorizationError(f"authorized field is not numeric: {bound.field_name}")
    for value in values:
        if bound.minimum is not None and value < bound.minimum:
            raise FeedbackOutOfBoundsError(f"{bound.field_name} below authorized minimum")
        if bound.maximum is not None and value > bound.maximum:
            raise FeedbackOutOfBoundsError(f"{bound.field_name} above authorized maximum")


def _validate_allowed_values(payload: dict[str, object], bound: AllowedValuesAuthorizationBound) -> None:
    if bound.field_name not in payload:
        raise FeedbackAuthorizationError(f"authorized enum field absent from payload: {bound.field_name}")
    raw_value = payload[bound.field_name]
    values = raw_value if isinstance(raw_value, tuple) else (raw_value,)
    allowed = set(bound.allowed_values)
    for value in values:
        text = value.value if hasattr(value, "value") else str(value)
        if text not in allowed:
            raise FeedbackOutOfBoundsError(f"{bound.field_name} contains unauthorized value: {text}")


def _validate_authority(
    feedback: PromotedFeedback,
    recommendation: P9FeedbackRecommendationV1,
    authorization: P0PolicyAuthorizationV1,
    *,
    current_sequence: int,
    decision_time: datetime,
) -> None:
    expected = (feedback.feedback_id, feedback.target_policy_id, feedback.effect_type)
    if (recommendation.feedback_id, recommendation.target_policy_id, recommendation.effect_type) != expected:
        raise FeedbackAuthorizationError("P9 recommendation does not match feedback")
    if (authorization.feedback_id, authorization.target_policy_id, authorization.effect_type) != expected:
        raise FeedbackAuthorizationError("P0 authorization does not match feedback")
    if recommendation.status is not FeedbackRecommendationStatus.PROMOTED:
        raise FeedbackAuthorizationError("P9 recommendation is not PROMOTED")
    if recommendation.source_cycle_sequence != feedback.source_cycle_sequence:
        raise FeedbackAuthorizationError("P9 recommendation source cycle mismatch")
    if recommendation.available_at > decision_time or authorization.available_at > decision_time:
        raise TemporalIntegrityError("feedback authority evidence was unavailable at decision_time")
    if authorization.valid_from_sequence > current_sequence:
        raise FeedbackAuthorizationError("P0 authorization is not yet valid")
    if authorization.expires_after_sequence is not None and current_sequence > authorization.expires_after_sequence:
        raise FeedbackAuthorizationError("P0 authorization is expired")
    payload = _payload_mapping(feedback)
    for bound in authorization.numeric_bounds:
        _validate_numeric_bound(payload, bound)
    for bound in authorization.allowed_values:
        _validate_allowed_values(payload, bound)


def _load_feedback(
    reference: ArtifactReference,
    *,
    store: ArtifactStorePort,
    context: S1ExecutionContext,
) -> PromotedFeedback:
    raw = read_verified_artifact(store, reference, decision_time=context.decision_time)
    load_json_object(raw)
    try:
        feedback = PROMOTED_FEEDBACK_ADAPTER.validate_json(raw, strict=True)
    except ValidationError as exc:
        raise FeedbackAuthorizationError(f"feedback schema validation failed: {exc}") from exc
    verify_model_embedded_hash(feedback)
    if feedback.available_at > context.decision_time:
        raise TemporalIntegrityError("feedback was not available at decision_time")
    return feedback


def run_module(
    feedback_refs: tuple[ArtifactReference, ...],
    *,
    store: ArtifactStorePort,
    idempotency_store: IdempotencyStorePort,
    context: S1ExecutionContext,
) -> M04Result:
    applied: list[PromotedFeedback] = []
    item_receipts: list[FeedbackItemReceipt] = []
    input_objects: list[object] = list(feedback_refs)
    for reference in feedback_refs:
        feedback = _load_feedback(reference, store=store, context=context)
        if feedback.target_cycle_sequence > context.cycle_sequence:
            raise FeedbackAuthorizationError("feedback targets a future cycle")
        if (
            feedback.target_cycle_sequence == context.cycle_sequence
            and feedback.target_cycle_id != context.cycle_id
        ):
            raise FeedbackAuthorizationError("feedback target cycle does not match current cycle")
        if idempotency_store.is_applied(feedback.idempotency_key):
            item_receipts.append(
                FeedbackItemReceipt(feedback_id=feedback.feedback_id, status=ReceiptStatus.ALREADY_APPLIED)
            )
            continue
        if context.cycle_sequence < feedback.effective_from_sequence:
            item_receipts.append(
                FeedbackItemReceipt(feedback_id=feedback.feedback_id, status=ReceiptStatus.NOT_EFFECTIVE_YET)
            )
            continue
        if feedback.expires_after_sequence is not None and context.cycle_sequence > feedback.expires_after_sequence:
            item_receipts.append(FeedbackItemReceipt(feedback_id=feedback.feedback_id, status=ReceiptStatus.EXPIRED))
            continue
        recommendation_raw = read_verified_artifact(
            store, feedback.p9_recommendation_ref, decision_time=context.decision_time
        )
        authorization_raw = read_verified_artifact(
            store, feedback.p0_authorization_ref, decision_time=context.decision_time
        )
        recommendation = validate_model_json(
            P9FeedbackRecommendationV1, recommendation_raw, label="P9 feedback recommendation"
        )
        authorization = validate_model_json(P0PolicyAuthorizationV1, authorization_raw, label="P0 authorization")
        _validate_authority(
            feedback,
            recommendation,
            authorization,
            current_sequence=context.cycle_sequence,
            decision_time=context.decision_time,
        )
        idempotency_store.mark_applied(feedback.idempotency_key)
        applied.append(feedback)
        item_receipts.append(FeedbackItemReceipt(feedback_id=feedback.feedback_id, status=ReceiptStatus.APPLIED))
        input_objects.extend((feedback, recommendation, authorization))
    feedback_context = PromotedPortfolioFeedbackContext(
        current_cycle_id=context.cycle_id,
        current_cycle_sequence=context.cycle_sequence,
        applied_feedback=tuple(applied),
        item_receipts=tuple(item_receipts),
    )
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        inputs=tuple(input_objects),
        output=feedback_context,
        computed_at=context.computed_at,
    )
    return M04Result(feedback_context=feedback_context, receipt=receipt)
