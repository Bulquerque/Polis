from .p3_s23_factories import bound_updates, config, current_belief_panel, current_person_panel, policy
from quant_pipeline.phase_03_agents_rag_memory.runtime.state_transition import guard_gradual_changes, write_person_state_transition


def test_p3_s23_integrated_vertical():
    persons, beliefs = write_person_state_transition(
        belief_updates=bound_updates(), current_person_states=current_person_panel(),
        current_beliefs=current_belief_panel(), person_policy=policy(), config=config(),
    )
    validated = guard_gradual_changes(
        candidates=persons, current_states=current_person_panel(), person_policy=policy(), config=config(),
    )
    assert validated.status == "READY"
    assert beliefs.records[0].belief_update_id == "update-1"
