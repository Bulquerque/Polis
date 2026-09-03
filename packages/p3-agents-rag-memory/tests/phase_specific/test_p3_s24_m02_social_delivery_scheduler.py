from quant_pipeline.phase_03_agents_rag_memory.runtime.social_delivery import (
    route_social_messages,
    schedule_social_delivery,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s24_models import DeliveryStatus

from .p3_s24_factories import config, graph, intents, person, states


def test_latency_boundary_and_next_cycle() -> None:
    cfg = config()
    message = route_social_messages(
        intents=intents(), social_graph=graph(), next_person_states=states(), config=cfg
    )
    delivery, events = schedule_social_delivery(messages=message, config=cfg)
    record = delivery.records[0]
    assert 60 <= record.latency_seconds <= 3600
    assert record.target_cycle_id == cfg.next_cycle_id
    assert [event.status.value for event in events.records] == ["CREATED", "QUEUED"]


def test_undelivered_is_preserved() -> None:
    cfg = config()
    state_panel = states(
        person("p1"),
        person("p2", attention={"social_receptivity": 0.8, "social_availability": 0.0}),
    )
    message = route_social_messages(
        intents=intents(), social_graph=graph(), next_person_states=state_panel, config=cfg
    )
    delivery, _ = schedule_social_delivery(messages=message, config=cfg)
    assert delivery.records[0].status is DeliveryStatus.UNDELIVERED
    assert delivery.records[0].scheduled_for is None
