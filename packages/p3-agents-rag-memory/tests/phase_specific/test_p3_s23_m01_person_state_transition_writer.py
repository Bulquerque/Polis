from .p3_s23_factories import bound_updates, config, current_belief_panel, current_person_panel, policy
from quant_pipeline.phase_03_agents_rag_memory.runtime.state_transition import write_person_state_transition


def test_m01_materializes_complete_states_and_caps():
    persons, beliefs = write_person_state_transition(
        belief_updates=bound_updates(), current_person_states=current_person_panel(),
        current_beliefs=current_belief_panel(), person_policy=policy(), config=config(),
    )
    assert persons.records[0].candidate_state.state_version == 2
    assert beliefs.records[0].state_origin == "UPDATED"
    assert persons.records[0].candidate_state.tool_proficiency == current_person_panel().records[0].tool_proficiency
    for change in persons.records[0].field_changes:
        assert abs(change.delta) <= change.allowed_delta + config().numeric_tolerance


def test_m01_replay_is_deterministic():
    def execute():
        return write_person_state_transition(
            belief_updates=bound_updates(), current_person_states=current_person_panel(),
            current_beliefs=current_belief_panel(), person_policy=policy(), config=config(),
        )
    first, second = execute(), execute()
    assert first[0].model_dump_json() == second[0].model_dump_json()
    assert first[1].model_dump_json() == second[1].model_dump_json()
