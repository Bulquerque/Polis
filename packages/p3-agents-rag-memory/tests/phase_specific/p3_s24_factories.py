from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus,
    FinalizedSocialIntentPanel,
    IntentStatus,
    LineageRecord,
    PersonToolEntitlementPanel,
    PersonToolEntitlementRecord,
    RequestValidationStatus,
    SocialIntentRecord,
    ToolCallRequestRecord,
    ToolOperationEntitlement,
    ValidatedToolCallRequestPanel,
    ValidatedToolCallRequestRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s23_models import (
    CurrentPersonStateRecord,
    PersonStateIdentity,
    ValidatedNextPersonStatePanel,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s24_models import (
    ChannelPolicy,
    ChannelVisibility,
    CurrentSocialGraph,
    SocialDeliveryConfig,
    SocialGraphEdgeRecord,
)

UTC = timezone.utc
AS_OF = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def lineage(name: str, producer: str = "test") -> LineageRecord:
    return LineageRecord(lineage_id=f"lineage-{name}", producer_module_id=producer)


def config(**updates) -> SocialDeliveryConfig:
    values = dict(
        run_id="run-1",
        current_cycle_id="cycle-10",
        next_cycle_id="cycle-11",
        as_of=AS_OF,
        next_cycle_start=AS_OF + timedelta(hours=1),
        next_cycle_end=AS_OF + timedelta(days=1),
        max_messages_per_person_cycle=5,
        default_channel_id="direct_message",
        message_type_channel_map={"ALERT": "direct_message"},
        evidence_required_message_types=("EVIDENCE_SHARE",),
        channel_policies=(
            ChannelPolicy(
                channel_id="direct_message",
                enabled=True,
                visibility=ChannelVisibility.DECLARED,
                base_latency_seconds=60,
                max_latency_seconds=3600,
            ),
            ChannelPolicy(
                channel_id="hidden_channel",
                enabled=True,
                visibility=ChannelVisibility.HIDDEN,
                base_latency_seconds=0,
                max_latency_seconds=0,
            ),
        ),
    )
    values.update(updates)
    return SocialDeliveryConfig(**values)


def person(person_id: str, *, attention: dict[str, float] | None = None) -> CurrentPersonStateRecord:
    return CurrentPersonStateRecord(
        person_state_id=f"state-{person_id}",
        person_id=person_id,
        profile_hash=f"profile-{person_id}",
        identity=PersonStateIdentity(
            life_stage_at_creation="adult",
            creator_provenance={"source": "fixture"},
        ),
        attention=attention
        if attention is not None
        else {"social_receptivity": 0.8, "social_availability": 0.9},
        updated_at=AS_OF,
        state_version=2,
    )


def states(*records: CurrentPersonStateRecord) -> ValidatedNextPersonStatePanel:
    values = records or (person("p1"), person("p2"))
    return ValidatedNextPersonStatePanel(
        status=ArtifactStatus.READY,
        records=tuple(values),
        lineage=lineage("states", "P3.S23.M02"),
    )


def edge(
    *,
    source: str = "p1",
    target: str = "p2",
    channels: tuple[str, ...] = ("direct_message",),
    strength: float = 0.75,
    available_at: datetime = AS_OF,
) -> SocialGraphEdgeRecord:
    return SocialGraphEdgeRecord(
        relationship_id=f"rel-{source}-{target}",
        source_person_id=source,
        target_person_id=target,
        relationship_strength=strength,
        allowed_channel_ids=channels,
        available_at=available_at,
    )


def graph(*records: SocialGraphEdgeRecord) -> CurrentSocialGraph:
    values = records or (edge(),)
    return CurrentSocialGraph(
        status=ArtifactStatus.READY,
        records=tuple(values),
        lineage=lineage("graph", "P3.S11.M03"),
    )


def intent(
    *,
    intent_id: str = "intent-1",
    sender: str = "p1",
    recipient: str | None = "p2",
    message_type: str = "ALERT",
    evidence_refs: tuple[str, ...] = ("ev-1",),
    status: IntentStatus = IntentStatus.FINALIZED,
) -> SocialIntentRecord:
    return SocialIntentRecord(
        intent_id=intent_id,
        cognition_transaction_id="tx-1",
        sender_person_id=sender,
        recipient_person_id=recipient,
        message_type=message_type,
        summary="Share a supported market observation.",
        claim_refs=("claim-1",),
        evidence_refs=evidence_refs,
        requested_action="review",
        status=status,
    )


def intents(*records: SocialIntentRecord) -> FinalizedSocialIntentPanel:
    values = records or (intent(),)
    return FinalizedSocialIntentPanel(
        status=ArtifactStatus.READY,
        records=tuple(values),
        lineage=lineage("intents", "P3.S21.M05"),
    )


def entitlement(
    *,
    person_id: str = "p1",
    tool_id: str = "social-research",
    operation_id: str = "social_lookup",
    provider_id: str = "provider-1",
    version: str = "ent-v1",
) -> PersonToolEntitlementRecord:
    return PersonToolEntitlementRecord(
        person_id=person_id,
        tool_id=tool_id,
        provider_id=provider_id,
        budget_calls_per_cycle=3,
        operations=(
            ToolOperationEntitlement(
                operation_id=operation_id,
                arguments_schema={"type": "object", "additionalProperties": False},
                result_schema={"type": "object"},
            ),
        ),
        entitlement_version=version,
    )


def entitlements(*records: PersonToolEntitlementRecord) -> PersonToolEntitlementPanel:
    values = records or (entitlement(),)
    return PersonToolEntitlementPanel(
        status=ArtifactStatus.READY,
        records=tuple(values),
        lineage=lineage("entitlements", "P3.S15.M02"),
    )


def request(
    *,
    request_id: str = "req-1",
    person_id: str = "p1",
    tool_id: str = "social-research",
    operation_id: str = "social_lookup",
    validation_status: RequestValidationStatus = RequestValidationStatus.ACCEPTED,
    provider_id: str | None = "provider-1",
    entitlement_version: str | None = "ent-v1",
) -> ValidatedToolCallRequestRecord:
    raw = ToolCallRequestRecord(
        tool_call_request_id=request_id,
        cognition_transaction_id="tx-1",
        person_id=person_id,
        tool_id=tool_id,
        operation_id=operation_id,
        arguments={},
        reason="Need supporting context",
        expected_information_gain=0.5,
        requested_at=AS_OF,
        as_of=AS_OF,
        idempotency_key=f"idem-{request_id}",
    )
    return ValidatedToolCallRequestRecord(
        request=raw,
        validation_status=validation_status,
        reason_codes=() if validation_status is RequestValidationStatus.ACCEPTED else (validation_status.value,),
        provider_id=provider_id,
        entitlement_version=entitlement_version,
        arguments_schema={"type": "object"},
        result_schema={"type": "object"},
        read_only=True,
        point_in_time_safe=True,
    )


def requests(*records: ValidatedToolCallRequestRecord) -> ValidatedToolCallRequestPanel:
    values = records or (request(),)
    return ValidatedToolCallRequestPanel(
        status=ArtifactStatus.READY,
        records=tuple(values),
        lineage=lineage("requests", "P3.S21.M02"),
    )
