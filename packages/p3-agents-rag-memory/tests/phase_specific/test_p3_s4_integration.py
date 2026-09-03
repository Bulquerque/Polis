from __future__ import annotations
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.governance_to_population import to_population_person_policy


def test_tag_registry_and_person_policy_share_canonical_ids(governance_outputs, operational_policy, objective_aliases):
    registry=governance_outputs["personality_tag_registry"]
    policy=to_population_person_policy(governance_outputs["person_schema_policy"],registry,operational_policy,objective_aliases)
    ids={tag["tag_id"] for category in registry["categories"] for tag in category["tags"]}
    assert ids
    assert policy.schema_id
    assert len(ids)==len(set(ids))
