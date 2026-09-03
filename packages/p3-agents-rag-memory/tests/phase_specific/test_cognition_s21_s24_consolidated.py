from __future__ import annotations

import pytest

from quant_pipeline.phase_03_agents_rag_memory.runtime.beliefs import (
    bind_evidence,
    log_commitments,
    validate_belief_state,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime.social_delivery import (
    audit_social_tool_usage,
    route_social_messages,
    schedule_social_delivery,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime.state_transition import (
    guard_gradual_changes,
    write_person_state_transition,
)
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s24_models import SocialToolAuditPolicy

from .p3_s21_helpers import run_through_m06
from .p3_s22_factories import (
    current_state,
    graph as belief_graph,
    policy as belief_policy,
    proposal_panel,
    rag,
    registry,
    retrieval,
    snapshot,
    tool_results,
)
from .p3_s23_factories import (
    bound_updates,
    config as state_config,
    current_belief_panel,
    current_person_panel,
    policy as person_policy,
)
from .p3_s24_factories import (
    config as social_config,
    entitlements,
    graph as social_graph,
    intents,
    requests,
    states,
)


@pytest.mark.asyncio
async def test_b2_all_four_subphases_are_functional() -> None:
    s21 = await run_through_m06()
    assert s21[-1]["structured_belief_proposal_panel"]["records"]

    validated = validate_belief_state(
        proposals=proposal_panel(),
        current_state=current_state(),
        snapshot=snapshot(),
        proposition_registry=registry(),
        policy=belief_policy(),
    )
    bounded = bind_evidence(
        updates=validated,
        retrieval=retrieval(),
        graph=belief_graph(),
        rag=rag(),
        tool_results=tool_results(),
        policy=belief_policy(),
    )
    commitments = log_commitments(
        bound_updates=bounded,
        snapshot=snapshot(),
        policy=belief_policy(),
    )
    assert len(commitments.records) == 1

    candidates, next_beliefs = write_person_state_transition(
        belief_updates=bound_updates(),
        current_person_states=current_person_panel(),
        current_beliefs=current_belief_panel(),
        person_policy=person_policy(),
        config=state_config(),
    )
    accepted = guard_gradual_changes(
        candidates=candidates,
        current_states=current_person_panel(),
        person_policy=person_policy(),
        config=state_config(),
    )
    assert accepted.status == "READY"
    assert next_beliefs.records

    cfg = social_config()
    messages = route_social_messages(
        intents=intents(),
        social_graph=social_graph(),
        next_person_states=states(),
        config=cfg,
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
