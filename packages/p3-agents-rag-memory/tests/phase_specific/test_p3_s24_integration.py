from quant_pipeline.phase_03_agents_rag_memory.runtime.social_delivery import (
    audit_social_tool_usage,
    route_social_messages,
    schedule_social_delivery,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s24_models import SocialToolAuditPolicy

from .p3_s24_factories import config, entitlements, graph, intents, requests, states


def test_p3_s24_vertical() -> None:
    cfg = config()
    messages = route_social_messages(
        intents=intents(), social_graph=graph(), next_person_states=states(), config=cfg
    )
    deliveries, events = schedule_social_delivery(messages=messages, config=cfg)
    audit = audit_social_tool_usage(
        deliveries=deliveries,
        requests=requests(),
        entitlements=entitlements(),
        policy=SocialToolAuditPolicy(),
    )
    assert len(messages.records) == len(deliveries.records) == 1
    assert [event.status.value for event in events.records] == ["CREATED", "QUEUED"]
    assert len(audit.records) == 1
