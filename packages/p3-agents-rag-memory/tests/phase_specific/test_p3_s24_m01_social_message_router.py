from quant_pipeline.phase_03_agents_rag_memory.runtime.social_delivery import route_social_messages
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import ArtifactStatus

from .p3_s24_factories import config, graph, intent, intents, states


def test_invalid_receiver_fails_materially() -> None:
    panel = route_social_messages(
        intents=intents(intent(recipient="missing")),
        social_graph=graph(),
        next_person_states=states(),
        config=config(),
    )
    assert panel.status is ArtifactStatus.FAILED
    assert panel.rejections[0].reason_codes == ("RECIPIENT_NOT_FOUND",)


def test_happy_path_routes_one_message() -> None:
    panel = route_social_messages(
        intents=intents(), social_graph=graph(), next_person_states=states(), config=config()
    )
    assert panel.status is ArtifactStatus.READY
    assert panel.records[0].target_cycle_id == "cycle-11"
