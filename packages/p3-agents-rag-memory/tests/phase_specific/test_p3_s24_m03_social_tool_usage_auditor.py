from quant_pipeline.phase_03_agents_rag_memory.runtime.social_delivery import (
    audit_social_tool_usage,
    route_social_messages,
    schedule_social_delivery,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import ArtifactStatus
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s24_models import (
    SocialToolAuditPolicy,
    SocialToolAuditStatus,
)

from .p3_s24_factories import config, entitlements, graph, intents, requests, states


def _deliveries():
    cfg = config()
    message = route_social_messages(
        intents=intents(), social_graph=graph(), next_person_states=states(), config=cfg
    )
    return schedule_social_delivery(messages=message, config=cfg)[0]


def test_unentitled_social_tool_fails_materially() -> None:
    empty = entitlements().model_copy(update={"records": (), "status": ArtifactStatus.EMPTY_VALID})
    panel = audit_social_tool_usage(
        deliveries=_deliveries(),
        requests=requests(),
        entitlements=empty,
        policy=SocialToolAuditPolicy(),
    )
    assert panel.records[0].audit_status is SocialToolAuditStatus.ENTITLEMENT_MISSING


def test_delivery_linkage_is_request_level_only() -> None:
    panel = audit_social_tool_usage(
        deliveries=_deliveries(),
        requests=requests(),
        entitlements=entitlements(),
        policy=SocialToolAuditPolicy(),
    )
    assert panel.records[0].audit_status is SocialToolAuditStatus.SOCIAL_OPERATION_CONFIRMED
    assert panel.records[0].request_level_only is True
