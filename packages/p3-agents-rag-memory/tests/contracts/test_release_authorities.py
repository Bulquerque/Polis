from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.orchestration.release_validation import (
    validate_documentation_links,
    validate_global_authority_patch,
    validate_schema_registry_hashes,
)

ROOT = Path(__file__).resolve().parents[2]


def test_schema_registries_are_hash_complete_and_identical() -> None:
    assert validate_schema_registry_hashes(ROOT) == []


def test_module_documentation_has_no_broken_owner_prompt() -> None:
    assert validate_documentation_links(ROOT) == []


def test_global_authority_patch_is_self_consistent() -> None:
    assert validate_global_authority_patch(ROOT) == []
