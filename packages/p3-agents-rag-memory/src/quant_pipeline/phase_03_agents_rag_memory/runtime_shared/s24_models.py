from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, JsonValue, model_validator

from .s21_models import (
    ArtifactStatus,
    FinalizedSocialIntentPanel,
    LineageRecord,
    NonEmptyStr,
    PersonToolEntitlementPanel,
    Probability,
    RequestValidationStatus,
    StrictModel,
    UTCDateTime,
    ValidatedToolCallRequestPanel,
)
from .s23_models import ValidatedNextPersonStatePanel

S24_SCHEMA_VERSION = "p3.s24.v1"


class ChannelVisibility(StrEnum):
    DECLARED = "DECLARED"
    HIDDEN = "HIDDEN"


class AttentionSource(StrEnum):
    STATE_VALUE = "STATE_VALUE"
    CONFIG_DEFAULT = "CONFIG_DEFAULT"


class AvailabilitySource(StrEnum):
    STATE_VALUE = "STATE_VALUE"
    CONFIG_DEFAULT = "CONFIG_DEFAULT"


class RoutingStatus(StrEnum):
    ROUTED = "ROUTED"
    REJECTED = "REJECTED"


class DeliveryStatus(StrEnum):
    QUEUED = "QUEUED"
    UNDELIVERED = "UNDELIVERED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class DeliveryEventStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    UNDELIVERED = "UNDELIVERED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class SocialToolAuditStatus(StrEnum):
    NO_ASSOCIATED_REQUEST = "NO_ASSOCIATED_REQUEST"
    SOCIAL_OPERATION_CONFIRMED = "SOCIAL_OPERATION_CONFIRMED"
    ASSOCIATED_REQUEST_ONLY = "ASSOCIATED_REQUEST_ONLY"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    ENTITLEMENT_MISSING = "ENTITLEMENT_MISSING"
    ENTITLEMENT_MISMATCH = "ENTITLEMENT_MISMATCH"
    HIDDEN_CHANNEL = "HIDDEN_CHANNEL"


RecordT = TypeVar("RecordT", bound=StrictModel)


class S24ArtifactPanel(StrictModel, Generic[RecordT]):
    schema_version: Literal[S24_SCHEMA_VERSION] = S24_SCHEMA_VERSION
    status: ArtifactStatus = ArtifactStatus.READY
    records: tuple[RecordT, ...]
    lineage: LineageRecord
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_empty_status(self) -> "S24ArtifactPanel[RecordT]":
        if not self.records and self.status not in {
            ArtifactStatus.EMPTY_VALID,
            ArtifactStatus.DEGRADED,
            ArtifactStatus.FAILED,
        }:
            raise ValueError("empty panels must declare EMPTY_VALID, DEGRADED, or FAILED")
        return self


class ChannelPolicy(StrictModel):
    channel_id: NonEmptyStr
    enabled: bool = True
    visibility: ChannelVisibility = ChannelVisibility.DECLARED
    base_latency_seconds: Annotated[int, Field(ge=0, le=604800)] = 0
    max_latency_seconds: Annotated[int, Field(ge=0, le=604800)] = 86400

    @model_validator(mode="after")
    def latency_bounds(self) -> "ChannelPolicy":
        if self.max_latency_seconds < self.base_latency_seconds:
            raise ValueError("max latency must be >= base latency")
        return self


class SocialDeliveryConfig(StrictModel):
    schema_version: Literal[S24_SCHEMA_VERSION] = S24_SCHEMA_VERSION
    config_version: NonEmptyStr = "s24-social-delivery-v1"
    run_id: NonEmptyStr
    current_cycle_id: NonEmptyStr
    next_cycle_id: NonEmptyStr
    as_of: UTCDateTime
    next_cycle_start: UTCDateTime
    next_cycle_end: UTCDateTime
    max_messages_per_person_cycle: Annotated[int, Field(ge=0, le=100)] = 5
    social_events_target_cycle: Literal["N_plus_1"] = "N_plus_1"
    undelivered_preserved: Literal[True] = True
    allow_self_message: bool = False
    allow_without_relationship: bool = False
    default_channel_id: NonEmptyStr = "direct_message"
    message_type_channel_map: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)
    evidence_required_message_types: tuple[NonEmptyStr, ...] = ()
    attention_metric_key: NonEmptyStr = "social_receptivity"
    availability_metric_key: NonEmptyStr = "social_availability"
    default_attention_score: Probability = 0.5
    default_availability_score: Probability = 1.0
    minimum_availability_score: Probability = 0.25
    relationship_latency_weight: Annotated[float, Field(ge=0.0, le=10.0)] = 1.0
    attention_latency_weight: Annotated[float, Field(ge=0.0, le=10.0)] = 1.0
    channel_policies: tuple[ChannelPolicy, ...]

    @model_validator(mode="after")
    def validate_window_and_channels(self) -> "SocialDeliveryConfig":
        if not self.as_of <= self.next_cycle_start <= self.next_cycle_end:
            raise ValueError("cycle window must satisfy as_of <= start <= end")
        channel_ids = [item.channel_id for item in self.channel_policies]
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError("duplicate channel policy")
        if self.default_channel_id not in set(channel_ids):
            raise ValueError("default channel is not configured")
        return self

    def channel(self, channel_id: str) -> ChannelPolicy:
        for policy in self.channel_policies:
            if policy.channel_id == channel_id:
                return policy
        raise ValueError(f"unknown channel: {channel_id}")


class SocialToolAuditPolicy(StrictModel):
    schema_version: Literal[S24_SCHEMA_VERSION] = S24_SCHEMA_VERSION
    policy_version: NonEmptyStr = "s24-social-tool-audit-v1"
    social_operation_prefixes: tuple[NonEmptyStr, ...] = (
        "social_",
        "message_",
        "communication_",
    )
    hidden_channels_forbidden: Literal[True] = True
    audit_scope: Literal["REQUEST_LEVEL_ONLY"] = "REQUEST_LEVEL_ONLY"


class SocialGraphEdgeRecord(StrictModel):
    relationship_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    directed: bool = True
    active: bool = True
    relationship_strength: Probability = 0.5
    allowed_channel_ids: tuple[NonEmptyStr, ...] = ("direct_message",)
    available_at: UTCDateTime

    def connects(self, sender_id: str, recipient_id: str) -> bool:
        if self.source_person_id == sender_id and self.target_person_id == recipient_id:
            return True
        return (
            not self.directed
            and self.source_person_id == recipient_id
            and self.target_person_id == sender_id
        )


class CurrentSocialGraph(S24ArtifactPanel[SocialGraphEdgeRecord]):
    pass


class SocialMessageRecord(StrictModel):
    message_id: NonEmptyStr
    run_id: NonEmptyStr
    source_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    intent_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    recipient_person_id: NonEmptyStr
    message_type: NonEmptyStr
    summary: NonEmptyStr
    claim_refs: tuple[NonEmptyStr, ...] = ()
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    requested_action: str | None = None
    relationship_id: NonEmptyStr | None = None
    relationship_strength: Probability
    channel_id: NonEmptyStr
    channel_visibility: ChannelVisibility
    recipient_attention_score: Probability
    attention_source: AttentionSource
    recipient_availability_score: Probability
    availability_source: AvailabilitySource
    created_at: UTCDateTime
    idempotency_key: NonEmptyStr
    routing_reason_codes: tuple[NonEmptyStr, ...] = ()


class RejectedSocialIntentRecord(StrictModel):
    intent_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    recipient_person_id: str | None = None
    reason_codes: tuple[NonEmptyStr, ...]


class SocialMessagePanel(StrictModel):
    schema_version: Literal[S24_SCHEMA_VERSION] = S24_SCHEMA_VERSION
    status: ArtifactStatus
    records: tuple[SocialMessageRecord, ...]
    rejections: tuple[RejectedSocialIntentRecord, ...] = ()
    lineage: LineageRecord
    reason_code: str | None = None


class SocialDeliveryRecord(StrictModel):
    delivery_id: NonEmptyStr
    message_id: NonEmptyStr
    run_id: NonEmptyStr
    source_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    recipient_person_id: NonEmptyStr
    channel_id: NonEmptyStr
    channel_visibility: ChannelVisibility
    relationship_id: NonEmptyStr | None = None
    status: DeliveryStatus
    scheduled_for: UTCDateTime | None = None
    delivery_window_end: UTCDateTime
    latency_seconds: Annotated[int, Field(ge=0)]
    delivery_attempt: Literal[0] = 0
    idempotency_key: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()


class SocialDeliveryPanel(S24ArtifactPanel[SocialDeliveryRecord]):
    pass


class SocialDeliveryEventRecord(StrictModel):
    specversion: Literal["1.0"] = "1.0"
    event_id: NonEmptyStr
    event_type: NonEmptyStr
    source: NonEmptyStr
    subject: NonEmptyStr
    event_time: UTCDateTime
    data_schema: NonEmptyStr = "urn:p3:schema:social-delivery-event:v1"
    delivery_id: NonEmptyStr
    message_id: NonEmptyStr
    correlation_id: NonEmptyStr
    causation_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    status: DeliveryEventStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()


class SocialDeliveryEventPanel(S24ArtifactPanel[SocialDeliveryEventRecord]):
    pass


class SocialToolAuditRecord(StrictModel):
    audit_id: NonEmptyStr
    delivery_id: NonEmptyStr
    message_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    channel_id: NonEmptyStr
    channel_visibility: ChannelVisibility
    tool_call_request_id: NonEmptyStr | None = None
    tool_id: NonEmptyStr | None = None
    operation_id: NonEmptyStr | None = None
    provider_id: NonEmptyStr | None = None
    entitlement_version: NonEmptyStr | None = None
    request_validation_status: RequestValidationStatus | None = None
    audit_status: SocialToolAuditStatus
    social_operation_confirmed: bool = False
    request_level_only: Literal[True] = True
    reason_codes: tuple[NonEmptyStr, ...] = ()


class SocialToolAuditPanel(S24ArtifactPanel[SocialToolAuditRecord]):
    pass


__all__ = [
    "AttentionSource",
    "AvailabilitySource",
    "ChannelPolicy",
    "ChannelVisibility",
    "CurrentSocialGraph",
    "DeliveryEventStatus",
    "DeliveryStatus",
    "FinalizedSocialIntentPanel",
    "PersonToolEntitlementPanel",
    "RejectedSocialIntentRecord",
    "RoutingStatus",
    "S24ArtifactPanel",
    "S24_SCHEMA_VERSION",
    "SocialDeliveryConfig",
    "SocialDeliveryEventPanel",
    "SocialDeliveryEventRecord",
    "SocialDeliveryPanel",
    "SocialDeliveryRecord",
    "SocialGraphEdgeRecord",
    "SocialMessagePanel",
    "SocialMessageRecord",
    "SocialToolAuditPanel",
    "SocialToolAuditPolicy",
    "SocialToolAuditRecord",
    "SocialToolAuditStatus",
    "ValidatedNextPersonStatePanel",
    "ValidatedToolCallRequestPanel",
]
