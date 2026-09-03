from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from .errors import ContractMismatchError
from .runtime import import_symbol, model_data


def _value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractMismatchError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractMismatchError(f"{field_name} must be a non-empty string")
    return value


def _validate_bounds(payload: Mapping[str, Any], authorization: Any) -> None:
    for bound in authorization.numeric_bounds:
        if bound.field_name not in payload:
            raise ContractMismatchError(f"authorized numeric field is absent: {bound.field_name}")
        value = Decimal(str(payload[bound.field_name]))
        if bound.minimum is not None and value < bound.minimum:
            raise ContractMismatchError(f"{bound.field_name} is below P0 authorization")
        if bound.maximum is not None and value > bound.maximum:
            raise ContractMismatchError(f"{bound.field_name} exceeds P0 authorization")
    for bound in authorization.allowed_values:
        if bound.field_name not in payload:
            raise ContractMismatchError(f"authorized categorical field is absent: {bound.field_name}")
        raw = payload[bound.field_name]
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        if any(str(item) not in set(bound.allowed_values) for item in values):
            raise ContractMismatchError(f"{bound.field_name} contains a value not authorized by P0")


def materialize_p8_promoted_feedback(
    *,
    p9_candidate: Any,
    concrete_payload: Mapping[str, Any],
    p9_recommendation: Any,
    p0_authorization: Any,
    p8_effect_type: str,
    p9_recommendation_ref: Any,
    p0_authorization_ref: Any,
    target_cycle_id: str,
    target_cycle_sequence: int,
    effective_from_sequence: int,
    idempotency_key: str,
    available_at: datetime,
) -> Any:
    contracts = "quant_pipeline.phase_08_contracts.p9"
    Recommendation = import_symbol(contracts, "P9FeedbackRecommendationV1")
    Authorization = import_symbol(contracts, "P0PolicyAuthorizationV1")
    adapter = import_symbol(contracts, "PROMOTED_FEEDBACK_ADAPTER")
    recommendation = Recommendation.model_validate(model_data(p9_recommendation), strict=False)
    authorization = Authorization.model_validate(model_data(p0_authorization), strict=False)
    candidate = model_data(p9_candidate)
    feedback_id = _required_text(candidate.get("feedback_id"), field_name="feedback_id")
    target_policy_id = _required_text(
        candidate.get("target_policy_id"), field_name="target_policy_id"
    )
    effect_type = _required_text(p8_effect_type, field_name="p8_effect_type")
    target_cycle_id = _required_text(target_cycle_id, field_name="target_cycle_id")
    idempotency_key = _required_text(idempotency_key, field_name="idempotency_key")
    available_at = _utc(available_at, field_name="available_at")
    if recommendation.feedback_id != feedback_id or authorization.feedback_id != feedback_id:
        raise ContractMismatchError("recommendation/authorization feedback IDs do not match candidate")
    if recommendation.target_policy_id != target_policy_id or authorization.target_policy_id != target_policy_id:
        raise ContractMismatchError("recommendation/authorization target policy does not match candidate")
    if _value(recommendation.effect_type) != effect_type or _value(authorization.effect_type) != effect_type:
        raise ContractMismatchError("recommendation/authorization effect type does not match candidate")
    if _value(recommendation.status) != "PROMOTED":
        raise ContractMismatchError("P8 materialization requires a promoted P9 recommendation")
    if effective_from_sequence < authorization.valid_from_sequence:
        raise ContractMismatchError("effective sequence precedes P0 authorization")
    if authorization.expires_after_sequence is not None and effective_from_sequence > authorization.expires_after_sequence:
        raise ContractMismatchError("P0 authorization has expired")
    _validate_bounds(concrete_payload, authorization)
    source_cycle = candidate.get("source_cycle")
    if not isinstance(source_cycle, Mapping):
        raise ContractMismatchError("P8 materialization requires explicit source_cycle")
    source_cycle_id = _required_text(source_cycle.get("cycle_id"), field_name="source_cycle.cycle_id")
    ordinal = source_cycle.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        raise ContractMismatchError("source_cycle.ordinal must be a non-negative integer")
    source_sequence = ordinal
    if source_sequence != recommendation.source_cycle_sequence:
        raise ContractMismatchError("candidate and recommendation source cycles do not match")
    if target_cycle_sequence <= source_sequence:
        raise ContractMismatchError("P8 feedback must target a later cycle")
    if effective_from_sequence < target_cycle_sequence:
        raise ContractMismatchError("effective sequence cannot precede target cycle")
    if available_at < recommendation.available_at.astimezone(UTC):
        raise ContractMismatchError("feedback cannot be available before the P9 recommendation")
    if available_at < authorization.available_at.astimezone(UTC):
        raise ContractMismatchError("feedback cannot be available before the P0 authorization")
    payload = {
        "feedback_id": feedback_id,
        "contract_version": "P9_TO_P8_PROMOTED_FEEDBACK_V1",
        "schema_version": "1.0.0",
        "source_cycle_id": source_cycle_id,
        "source_cycle_sequence": source_sequence,
        "target_cycle_id": target_cycle_id,
        "target_cycle_sequence": target_cycle_sequence,
        "target_policy_id": target_policy_id,
        "effect_type": effect_type,
        "payload": dict(concrete_payload),
        "p9_recommendation_ref": model_data(p9_recommendation_ref),
        "p0_authorization_ref": model_data(p0_authorization_ref),
        "effective_from_sequence": effective_from_sequence,
        "expires_after_sequence": authorization.expires_after_sequence,
        "idempotency_key": idempotency_key,
        "available_at": available_at,
    }
    payload["content_sha256"] = "0" * 64
    provisional = adapter.validate_python(payload, strict=False)
    finalize_content_hash = import_symbol(
        "quant_pipeline.phase_08_contracts.canonical", "finalize_content_hash"
    )
    return finalize_content_hash(provisional)
