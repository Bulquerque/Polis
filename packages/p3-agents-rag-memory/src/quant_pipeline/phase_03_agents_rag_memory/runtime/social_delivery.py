from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import timedelta
from math import ceil

from ..runtime_shared.s21_models import (
    ArtifactStatus,
    FinalizedSocialIntentPanel,
    IntentStatus,
    LineageRecord,
    PersonToolEntitlementPanel,
    RequestValidationStatus,
    ValidatedToolCallRequestPanel,
)
from ..runtime_shared.s23_models import ValidatedNextPersonStatePanel
from ..runtime_shared.s24_errors import S24InvariantError, S24TemporalError
from ..runtime_shared.s24_hashing import stable_id
from ..runtime_shared.s24_models import (
    AttentionSource,
    AvailabilitySource,
    ChannelVisibility,
    CurrentSocialGraph,
    DeliveryEventStatus,
    DeliveryStatus,
    RejectedSocialIntentRecord,
    SocialDeliveryConfig,
    SocialDeliveryEventPanel,
    SocialDeliveryEventRecord,
    SocialDeliveryPanel,
    SocialDeliveryRecord,
    SocialMessagePanel,
    SocialMessageRecord,
    SocialToolAuditPanel,
    SocialToolAuditPolicy,
    SocialToolAuditRecord,
    SocialToolAuditStatus,
)

FORBIDDEN_CONTENT_KEYS = frozenset(
    {
        "future_return",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
    }
)


def _panel_status(*, accepted: int, rejected: int) -> ArtifactStatus:
    if accepted == 0 and rejected == 0:
        return ArtifactStatus.EMPTY_VALID
    if accepted and rejected:
        return ArtifactStatus.DEGRADED
    if accepted:
        return ArtifactStatus.READY
    return ArtifactStatus.FAILED


def _unique_by(items: Iterable[object], key_getter, *, code: str, module_id: str) -> dict[object, object]:
    result: dict[object, object] = {}
    for item in items:
        key = key_getter(item)
        if key in result:
            raise S24InvariantError(code=code, message=f"duplicate key: {key}", module_id=module_id)
        result[key] = item
    return result


def _find_relationship(
    graph: CurrentSocialGraph,
    sender_id: str,
    recipient_id: str,
    *,
    as_of,
):
    candidates = [
        edge
        for edge in graph.records
        if edge.active and edge.connects(sender_id, recipient_id)
    ]
    for edge in candidates:
        if edge.available_at > as_of:
            raise S24TemporalError(
                code="FUTURE_SOCIAL_EDGE",
                message=edge.relationship_id,
                module_id="P3.S24.M01",
            )
    if len(candidates) > 1:
        raise S24InvariantError(
            code="MULTIPLE_ACTIVE_RELATIONSHIPS",
            message=f"{sender_id}->{recipient_id}",
            module_id="P3.S24.M01",
        )
    return candidates[0] if candidates else None


def _selected_channel(intent, relationship, config: SocialDeliveryConfig) -> str:
    configured = config.message_type_channel_map.get(intent.message_type, config.default_channel_id)
    policy = config.channel(configured)
    if not policy.enabled:
        raise ValueError("CHANNEL_DISABLED")
    if relationship is not None and configured not in set(relationship.allowed_channel_ids):
        raise ValueError("CHANNEL_NOT_ALLOWED_BY_RELATIONSHIP")
    return configured



def _routing_decision(intent, persons, social_graph, sender_counts, config):
    reasons: list[str] = []
    if intent.status is not IntentStatus.FINALIZED:
        reasons.append("INTENT_NOT_FINALIZED")
    sender = persons.get(intent.sender_person_id)
    if sender is None:
        reasons.append("SENDER_NOT_FOUND")
    recipient_id = intent.recipient_person_id
    recipient = persons.get(recipient_id) if recipient_id else None
    if not recipient_id:
        reasons.append("RECIPIENT_REQUIRED")
    elif recipient is None:
        reasons.append("RECIPIENT_NOT_FOUND")
    if recipient_id == intent.sender_person_id and not config.allow_self_message:
        reasons.append("SELF_MESSAGE_FORBIDDEN")
    if intent.message_type in set(config.evidence_required_message_types) and not intent.evidence_refs:
        reasons.append("EVIDENCE_REQUIRED")
    if any(key in intent.summary.lower() for key in FORBIDDEN_CONTENT_KEYS):
        reasons.append("FORBIDDEN_FIELD_TEXT")
    if sender_counts[intent.sender_person_id] >= config.max_messages_per_person_cycle:
        reasons.append("MESSAGE_BUDGET_EXCEEDED")
    relationship = None
    if recipient_id and sender is not None and recipient is not None:
        relationship = _find_relationship(social_graph, intent.sender_person_id, recipient_id, as_of=config.as_of)
        if relationship is None and not config.allow_without_relationship:
            reasons.append("ACTIVE_RELATIONSHIP_REQUIRED")
    channel_id = None
    if not reasons:
        try:
            channel_id = _selected_channel(intent, relationship, config)
        except ValueError as exc:
            reasons.append(str(exc))
    return sender, recipient, recipient_id, relationship, channel_id, reasons


def _rejected_intent(intent, recipient_id, reasons):
    return RejectedSocialIntentRecord(
        intent_id=intent.intent_id,
        cognition_transaction_id=intent.cognition_transaction_id,
        sender_person_id=intent.sender_person_id,
        recipient_person_id=recipient_id,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _recipient_routing_scores(recipient, config):
    reasons: list[str] = []
    attention = recipient.attention.get(config.attention_metric_key)
    attention_source = AttentionSource.STATE_VALUE
    if attention is None:
        attention = config.default_attention_score
        attention_source = AttentionSource.CONFIG_DEFAULT
        reasons.append("DEFAULT_ATTENTION_SCORE_USED")
    availability = recipient.attention.get(config.availability_metric_key)
    availability_source = AvailabilitySource.STATE_VALUE
    if availability is None:
        availability = config.default_availability_score
        availability_source = AvailabilitySource.CONFIG_DEFAULT
        reasons.append("DEFAULT_AVAILABILITY_SCORE_USED")
    return attention, attention_source, availability, availability_source, reasons


def _build_social_message(intent, recipient, recipient_id, relationship, channel_id, config):
    attention, attention_source, availability, availability_source, reasons = _recipient_routing_scores(recipient, config)
    message_id = stable_id(
        "social-message", config.run_id, config.current_cycle_id, intent.intent_id,
        intent.sender_person_id, recipient_id, channel_id,
    )
    return SocialMessageRecord(
        message_id=message_id, run_id=config.run_id,
        source_cycle_id=config.current_cycle_id, target_cycle_id=config.next_cycle_id,
        intent_id=intent.intent_id, cognition_transaction_id=intent.cognition_transaction_id,
        sender_person_id=intent.sender_person_id, recipient_person_id=recipient_id,
        message_type=intent.message_type, summary=intent.summary,
        claim_refs=tuple(sorted(set(intent.claim_refs))), evidence_refs=tuple(sorted(set(intent.evidence_refs))),
        requested_action=intent.requested_action,
        relationship_id=relationship.relationship_id if relationship else None,
        relationship_strength=relationship.relationship_strength if relationship else 0.0,
        channel_id=channel_id, channel_visibility=config.channel(channel_id).visibility,
        recipient_attention_score=attention, attention_source=attention_source,
        recipient_availability_score=availability, availability_source=availability_source,
        created_at=config.as_of, idempotency_key=stable_id("social-message-idempotency", message_id),
        routing_reason_codes=tuple(reasons),
    )


def route_social_messages(
    *, intents: FinalizedSocialIntentPanel, social_graph: CurrentSocialGraph,
    next_person_states: ValidatedNextPersonStatePanel, config: SocialDeliveryConfig,
) -> SocialMessagePanel:
    persons = _unique_by(next_person_states.records, lambda item: item.person_id, code="DUPLICATE_PERSON_STATE", module_id="P3.S24.M01")
    _unique_by(social_graph.records, lambda item: item.relationship_id, code="DUPLICATE_RELATIONSHIP", module_id="P3.S24.M01")
    sender_counts: Counter[str] = Counter()
    messages: list[SocialMessageRecord] = []
    rejections: list[RejectedSocialIntentRecord] = []
    for intent in sorted(intents.records, key=lambda item: item.intent_id):
        _, recipient, recipient_id, relationship, channel_id, reasons = _routing_decision(
            intent, persons, social_graph, sender_counts, config
        )
        if reasons:
            rejections.append(_rejected_intent(intent, recipient_id, reasons))
            continue
        assert recipient is not None and recipient_id is not None and channel_id is not None
        messages.append(_build_social_message(intent, recipient, recipient_id, relationship, channel_id, config))
        sender_counts[intent.sender_person_id] += 1
    sources = tuple(sorted({intents.lineage.lineage_id, social_graph.lineage.lineage_id, next_person_states.lineage.lineage_id}))
    lineage = LineageRecord(
        lineage_id=stable_id("lineage-s24-m01", *sources, config.config_version),
        source_artifact_ids=sources, producer_module_id="P3.S24.M01",
    )
    return SocialMessagePanel(
        status=_panel_status(accepted=len(messages), rejected=len(rejections)),
        records=tuple(messages), rejections=tuple(rejections), lineage=lineage,
        reason_code="DECLARED_CONFIG_DEFAULTS_USED" if any(m.routing_reason_codes for m in messages) else None,
    )

def _latency_seconds(message: SocialMessageRecord, config: SocialDeliveryConfig) -> int:
    policy = config.channel(message.channel_id)
    relationship_factor = 1.0 + config.relationship_latency_weight * (1.0 - message.relationship_strength)
    attention_factor = 1.0 + config.attention_latency_weight * (1.0 - message.recipient_attention_score)
    calculated = ceil(policy.base_latency_seconds * relationship_factor * attention_factor)
    return min(policy.max_latency_seconds, max(policy.base_latency_seconds, calculated))



def _validate_message_schedule(message: SocialMessageRecord, config: SocialDeliveryConfig) -> None:
    if message.run_id != config.run_id or message.source_cycle_id != config.current_cycle_id:
        raise S24InvariantError(code="MESSAGE_RUN_CYCLE_MISMATCH", message=message.message_id, module_id="P3.S24.M02")
    if message.target_cycle_id != config.next_cycle_id:
        raise S24InvariantError(code="SAME_CYCLE_OR_WRONG_TARGET", message=message.message_id, module_id="P3.S24.M02")
    if message.created_at > config.as_of:
        raise S24TemporalError(code="MESSAGE_CREATED_AFTER_AS_OF", message=message.message_id, module_id="P3.S24.M02")


def _delivery_record(message: SocialMessageRecord, config: SocialDeliveryConfig) -> SocialDeliveryRecord:
    _validate_message_schedule(message, config)
    latency = _latency_seconds(message, config)
    candidate_time = max(config.next_cycle_start, message.created_at + timedelta(seconds=latency))
    reasons: list[str] = []
    if message.recipient_availability_score < config.minimum_availability_score:
        status, scheduled_for = DeliveryStatus.UNDELIVERED, None
        reasons.append("RECIPIENT_UNAVAILABLE")
    elif candidate_time > config.next_cycle_end:
        status, scheduled_for = DeliveryStatus.UNDELIVERED, None
        reasons.append("OUTSIDE_NEXT_CYCLE_WINDOW")
    else:
        status, scheduled_for = DeliveryStatus.QUEUED, candidate_time
    delivery_id = stable_id("social-delivery", message.message_id, config.next_cycle_id)
    return SocialDeliveryRecord(
        delivery_id=delivery_id, message_id=message.message_id, run_id=message.run_id,
        source_cycle_id=message.source_cycle_id, target_cycle_id=message.target_cycle_id,
        cognition_transaction_id=message.cognition_transaction_id,
        sender_person_id=message.sender_person_id, recipient_person_id=message.recipient_person_id,
        channel_id=message.channel_id, channel_visibility=message.channel_visibility,
        relationship_id=message.relationship_id, status=status, scheduled_for=scheduled_for,
        delivery_window_end=config.next_cycle_end, latency_seconds=latency,
        idempotency_key=stable_id("social-delivery-idempotency", delivery_id), reason_codes=tuple(reasons),
    )


def _delivery_events(message: SocialMessageRecord, delivery: SocialDeliveryRecord, config: SocialDeliveryConfig):
    created = SocialDeliveryEventRecord(
        event_id=stable_id("social-delivery-event", delivery.delivery_id, "CREATED"),
        event_type="org.quantpipeline.p3.social_delivery.created.v1", source="urn:quant-pipeline:p3:s24",
        subject=f"person/{message.recipient_person_id}", event_time=message.created_at,
        delivery_id=delivery.delivery_id, message_id=message.message_id,
        correlation_id=message.cognition_transaction_id, causation_id=message.intent_id,
        target_cycle_id=message.target_cycle_id, status=DeliveryEventStatus.CREATED, reason_codes=(),
    )
    event_status = DeliveryEventStatus.QUEUED if delivery.status is DeliveryStatus.QUEUED else DeliveryEventStatus.UNDELIVERED
    terminal = SocialDeliveryEventRecord(
        event_id=stable_id("social-delivery-event", delivery.delivery_id, event_status.value),
        event_type=f"org.quantpipeline.p3.social_delivery.{event_status.value.lower()}.v1",
        source="urn:quant-pipeline:p3:s24", subject=f"person/{message.recipient_person_id}",
        event_time=delivery.scheduled_for or config.as_of, delivery_id=delivery.delivery_id,
        message_id=message.message_id, correlation_id=message.cognition_transaction_id,
        causation_id=message.intent_id, target_cycle_id=message.target_cycle_id,
        status=event_status, reason_codes=delivery.reason_codes,
    )
    _validate_initial_delivery_lifecycle(created, terminal)
    return created, terminal


def _delivery_panel_status(deliveries, config: SocialDeliveryConfig) -> ArtifactStatus:
    if not deliveries:
        return ArtifactStatus.EMPTY_VALID
    if all(item.status is DeliveryStatus.QUEUED for item in deliveries):
        return ArtifactStatus.READY
    if any(item.status is DeliveryStatus.QUEUED for item in deliveries):
        return ArtifactStatus.DEGRADED
    return ArtifactStatus.DEGRADED if config.undelivered_preserved else ArtifactStatus.FAILED


def schedule_social_delivery(
    *, messages: SocialMessagePanel, config: SocialDeliveryConfig,
) -> tuple[SocialDeliveryPanel, SocialDeliveryEventPanel]:
    deliveries: list[SocialDeliveryRecord] = []
    events: list[SocialDeliveryEventRecord] = []
    for message in sorted(messages.records, key=lambda item: item.message_id):
        delivery = _delivery_record(message, config)
        deliveries.append(delivery)
        events.extend(_delivery_events(message, delivery, config))
    source_ids = (messages.lineage.lineage_id,)
    status = _delivery_panel_status(deliveries, config)
    return (
        SocialDeliveryPanel(status=status, records=tuple(deliveries), lineage=LineageRecord(
            lineage_id=stable_id("lineage-s24-m02-delivery", *source_ids, config.config_version),
            source_artifact_ids=source_ids, producer_module_id="P3.S24.M02")),
        SocialDeliveryEventPanel(status=status, records=tuple(events), lineage=LineageRecord(
            lineage_id=stable_id("lineage-s24-m02-events", *source_ids, config.config_version),
            source_artifact_ids=source_ids, producer_module_id="P3.S24.M02")),
    )

def _validate_initial_delivery_lifecycle(
    created: SocialDeliveryEventRecord,
    terminal: SocialDeliveryEventRecord,
) -> None:
    """Reject lifecycle jumps before delivery events are persisted."""

    if created.status is not DeliveryEventStatus.CREATED:
        raise S24InvariantError(
            code="DELIVERY_LIFECYCLE_MISSING_CREATED",
            message=created.delivery_id,
            module_id="P3.S24.M02",
        )
    if terminal.status not in {
        DeliveryEventStatus.QUEUED,
        DeliveryEventStatus.UNDELIVERED,
        DeliveryEventStatus.EXPIRED,
        DeliveryEventStatus.FAILED,
    }:
        raise S24InvariantError(
            code="DELIVERY_LIFECYCLE_ILLEGAL_TRANSITION",
            message=f"{created.status.value}->{terminal.status.value}",
            module_id="P3.S24.M02",
        )
    if created.delivery_id != terminal.delivery_id:
        raise S24InvariantError(
            code="DELIVERY_LIFECYCLE_ID_MISMATCH",
            message=created.delivery_id,
            module_id="P3.S24.M02",
        )
    if terminal.event_time < created.event_time:
        raise S24TemporalError(
            code="DELIVERY_LIFECYCLE_TIME_REVERSAL",
            message=created.delivery_id,
            module_id="P3.S24.M02",
        )



def _social_entitlement_index(entitlements: PersonToolEntitlementPanel) -> dict[tuple[str, str, str], object]:
    result: dict[tuple[str, str, str], object] = {}
    for entitlement in entitlements.records:
        for operation in entitlement.operations:
            key = (entitlement.person_id, entitlement.tool_id, operation.operation_id)
            if key in result:
                raise S24InvariantError(
                    code="DUPLICATE_ENTITLEMENT_OPERATION",
                    message=str(key),
                    module_id="P3.S24.M03",
                )
            result[key] = entitlement
    return result


def _no_request_audit(delivery) -> SocialToolAuditRecord:
    status = (
        SocialToolAuditStatus.HIDDEN_CHANNEL
        if delivery.channel_visibility is ChannelVisibility.HIDDEN
        else SocialToolAuditStatus.NO_ASSOCIATED_REQUEST
    )
    return SocialToolAuditRecord(
        audit_id=stable_id("social-tool-audit", delivery.delivery_id, "none"),
        delivery_id=delivery.delivery_id,
        message_id=delivery.message_id,
        cognition_transaction_id=delivery.cognition_transaction_id,
        sender_person_id=delivery.sender_person_id,
        channel_id=delivery.channel_id,
        channel_visibility=delivery.channel_visibility,
        audit_status=status,
        reason_codes=("NO_REQUEST_LINKED_TO_TRANSACTION",),
    )


def _linked_request_status(delivery, validated, entitlement_index, policy):
    request = validated.request
    reasons: list[str] = []
    if delivery.channel_visibility is ChannelVisibility.HIDDEN:
        return SocialToolAuditStatus.HIDDEN_CHANNEL, ["HIDDEN_CHANNEL_FORBIDDEN"]
    if validated.validation_status is not RequestValidationStatus.ACCEPTED:
        return SocialToolAuditStatus.REQUEST_REJECTED, list(
            validated.reason_codes or (validated.validation_status.value,)
        )
    entitlement = entitlement_index.get(
        (request.person_id, request.tool_id, request.operation_id)
    )
    if entitlement is None:
        return SocialToolAuditStatus.ENTITLEMENT_MISSING, ["ENTITLEMENT_OPERATION_NOT_FOUND"]
    if (
        validated.provider_id != entitlement.provider_id
        or validated.entitlement_version != entitlement.entitlement_version
    ):
        return SocialToolAuditStatus.ENTITLEMENT_MISMATCH, ["VALIDATED_REQUEST_ENTITLEMENT_MISMATCH"]
    confirmed = request.operation_id.startswith(policy.social_operation_prefixes)
    if confirmed:
        return SocialToolAuditStatus.SOCIAL_OPERATION_CONFIRMED, reasons
    return SocialToolAuditStatus.ASSOCIATED_REQUEST_ONLY, ["REQUEST_ASSOCIATED_BY_TRANSACTION_ONLY"]


def _linked_request_audit(delivery, validated, entitlement_index, policy) -> SocialToolAuditRecord:
    request = validated.request
    status, reasons = _linked_request_status(delivery, validated, entitlement_index, policy)
    return SocialToolAuditRecord(
        audit_id=stable_id("social-tool-audit", delivery.delivery_id, request.tool_call_request_id),
        delivery_id=delivery.delivery_id,
        message_id=delivery.message_id,
        cognition_transaction_id=delivery.cognition_transaction_id,
        sender_person_id=delivery.sender_person_id,
        channel_id=delivery.channel_id,
        channel_visibility=delivery.channel_visibility,
        tool_call_request_id=request.tool_call_request_id,
        tool_id=request.tool_id,
        operation_id=request.operation_id,
        provider_id=validated.provider_id,
        entitlement_version=validated.entitlement_version,
        request_validation_status=validated.validation_status,
        audit_status=status,
        social_operation_confirmed=status is SocialToolAuditStatus.SOCIAL_OPERATION_CONFIRMED,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _social_audit_status(audits: list[SocialToolAuditRecord]) -> ArtifactStatus:
    if not audits:
        return ArtifactStatus.EMPTY_VALID
    degraded = {
        SocialToolAuditStatus.ENTITLEMENT_MISSING,
        SocialToolAuditStatus.ENTITLEMENT_MISMATCH,
        SocialToolAuditStatus.HIDDEN_CHANNEL,
    }
    return ArtifactStatus.DEGRADED if any(a.audit_status in degraded for a in audits) else ArtifactStatus.READY


def audit_social_tool_usage(
    *,
    deliveries: SocialDeliveryPanel,
    requests: ValidatedToolCallRequestPanel,
    entitlements: PersonToolEntitlementPanel,
    policy: SocialToolAuditPolicy,
) -> SocialToolAuditPanel:
    entitlement_index = _social_entitlement_index(entitlements)
    by_transaction: dict[tuple[str, str], list] = defaultdict(list)
    for request in requests.records:
        by_transaction[(request.request.cognition_transaction_id, request.request.person_id)].append(request)
    audits: list[SocialToolAuditRecord] = []
    for delivery in sorted(deliveries.records, key=lambda item: item.delivery_id):
        linked = sorted(
            by_transaction.get((delivery.cognition_transaction_id, delivery.sender_person_id), []),
            key=lambda item: item.request.tool_call_request_id,
        )
        if not linked:
            audits.append(_no_request_audit(delivery))
        else:
            audits.extend(
                _linked_request_audit(delivery, validated, entitlement_index, policy)
                for validated in linked
            )
    source_ids = tuple(sorted({
        deliveries.lineage.lineage_id,
        requests.lineage.lineage_id,
        entitlements.lineage.lineage_id,
    }))
    return SocialToolAuditPanel(
        status=_social_audit_status(audits),
        records=tuple(audits),
        lineage=LineageRecord(
            lineage_id=stable_id("lineage-s24-m03", *source_ids, policy.policy_version),
            source_artifact_ids=source_ids,
            producer_module_id="P3.S24.M03",
        ),
    )
