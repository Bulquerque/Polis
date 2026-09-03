def test_registry_has_unique_canonical_ids_and_aliases(governance_outputs):
    registry = governance_outputs["personality_tag_registry"]
    ids = [tag["tag_id"] for category in registry["categories"] for tag in category["tags"]]
    aliases = [alias for category in registry["categories"] for tag in category["tags"] for alias in tag.get("aliases", [])]
    assert len(ids) == len(set(ids))
    assert len(aliases) == len(set(aliases))
    assert not (set(ids) & set(aliases))
