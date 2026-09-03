import pytest
from pydantic import ValidationError
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_population import to_population_person_policy


def test_person_policy_is_strict_and_uses_canonical_fields(governance_outputs, operational_policy, objective_aliases):
    policy = to_population_person_policy(governance_outputs["person_schema_policy"], governance_outputs["personality_tag_registry"], operational_policy, objective_aliases)
    payload = policy.model_dump(mode="json")
    assert payload["schema_id"]
    with pytest.raises(ValidationError):
        type(policy).model_validate({**payload, "unknown_field": True})
