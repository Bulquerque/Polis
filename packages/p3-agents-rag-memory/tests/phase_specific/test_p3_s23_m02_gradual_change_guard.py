from .p3_s23_factories import bound_updates, config, current_belief_panel, current_person_panel, policy
from quant_pipeline.phase_03_agents_rag_memory.runtime.state_transition import guard_gradual_changes, write_person_state_transition


def candidate_panel():
    return write_person_state_transition(
        belief_updates=bound_updates(), current_person_states=current_person_panel(),
        current_beliefs=current_belief_panel(), person_policy=policy(), config=config(),
    )[0]


def test_m02_accepts_writer_output():
    result = guard_gradual_changes(
        candidates=candidate_panel(), current_states=current_person_panel(),
        person_policy=policy(), config=config(),
    )
    assert result.status == "READY"
    assert len(result.records) == 1


def test_m02_rejects_immutable_change_without_repair():
    panel = candidate_panel(); record = panel.records[0]
    state = record.candidate_state.model_copy(update={"profile_hash": "changed"})
    bad = panel.model_copy(update={"records": (record.model_copy(update={"candidate_state": state}),)})
    result = guard_gradual_changes(
        candidates=bad, current_states=current_person_panel(), person_policy=policy(), config=config(),
    )
    assert not result.records
    assert "IMMUTABLE_PROFILE_HASH_CHANGED" in result.rejections[0].reason_codes
