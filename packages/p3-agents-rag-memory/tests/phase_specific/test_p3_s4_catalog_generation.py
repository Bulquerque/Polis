from quant_pipeline.phase_03_agents_rag_memory.foundation.person_foundation.catalog import (
    render_tag_registry_markdown,
    tag_registry_catalog,
)


def test_tag_catalog_and_documentation_come_from_runtime_registry(governance_outputs):
    registry = governance_outputs["personality_tag_registry"]
    catalog = tag_registry_catalog(registry)
    assert catalog["source_registry_hash"] == registry["registry_hash"]
    assert catalog["catalog_hash"]
    assert set(catalog["alias_to_tag"]).isdisjoint(registry["tag_to_category"])
    markdown = render_tag_registry_markdown(registry)
    assert registry["registry_id"] in markdown
    assert all(tag_id in markdown for tag_id in registry["tag_to_category"])
