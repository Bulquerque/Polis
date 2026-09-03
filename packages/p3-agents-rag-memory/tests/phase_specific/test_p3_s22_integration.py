from quant_pipeline.phase_03_agents_rag_memory.runtime.beliefs import bind_evidence, log_commitments, validate_belief_state
from .p3_s22_factories import current_state, graph, policy, proposal_panel, rag, registry, retrieval, snapshot, tool_results


def test_p3_s22_integrated_vertical():
    validated=validate_belief_state(proposals=proposal_panel(),current_state=current_state(),snapshot=snapshot(),proposition_registry=registry(),policy=policy())
    bounded=bind_evidence(updates=validated,retrieval=retrieval(),graph=graph(),rag=rag(),tool_results=tool_results(),policy=policy())
    log=log_commitments(bound_updates=bounded,snapshot=snapshot(),policy=policy())
    assert len(log.records)==1


def test_overlapping_support_and_opposition_is_not_committed():
    from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s22_models import EvidenceBindingStatus
    validated = validate_belief_state(
        proposals=proposal_panel(evidence=("ev-1",), opposing=("ev-1",)),
        current_state=current_state(),
        snapshot=snapshot(),
        proposition_registry=registry(),
        policy=policy(),
    )
    bounded = bind_evidence(
        updates=validated,
        retrieval=retrieval(),
        graph=graph(),
        rag=rag(),
        tool_results=tool_results(),
        policy=policy(),
    )
    assert bounded.records[0].binding_status is EvidenceBindingStatus.SUPPORT_OPPOSITION_OVERLAP
    log = log_commitments(bound_updates=bounded, snapshot=snapshot(), policy=policy())
    assert log.records == ()


def test_commitment_is_rejected_after_maturity():
    from datetime import timedelta
    from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s22_errors import S22TemporalError
    proposal_time = snapshot().as_of
    late_snapshot = snapshot(as_of=proposal_time + timedelta(days=2))
    validated = validate_belief_state(
        proposals=proposal_panel(generated_at=proposal_time),
        current_state=current_state(),
        snapshot=late_snapshot,
        proposition_registry=registry(),
        policy=policy(),
    )
    bounded = bind_evidence(
        updates=validated,
        retrieval=retrieval(),
        graph=graph(),
        rag=rag(),
        tool_results=tool_results(),
        policy=policy(),
    )
    with __import__("pytest").raises(S22TemporalError, match="LATE_COMMITMENT"):
        log_commitments(bound_updates=bounded, snapshot=late_snapshot, policy=policy())
