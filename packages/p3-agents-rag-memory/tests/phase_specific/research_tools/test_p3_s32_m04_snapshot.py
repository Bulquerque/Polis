from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.contracts.artifacts import ContractPackFile
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s32 import build_extension_snapshot

from .support import build_m01, build_m02, build_m03, build_m04, load_yaml


def snapshot_inputs():
    m01 = build_m01(); m02 = build_m02(m01); m03 = build_m03(m01)
    return {**m01, **m02, **m03,
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "prompt_descriptor_template_manifest": load_yaml("config/research_tools/PROMPT_DESCRIPTOR_TEMPLATE_MANIFEST.yaml"),
        "extension_config_manifest": load_yaml("config/research_tools/EXTENSION_CONFIG_MANIFEST.yaml")}


def test_snapshot_and_manifest_are_deterministic():
    first = build_m04(); second = build_m04()
    assert first == second
    assert first["research_tool_extension_snapshot"]["snapshot_hash"] == second["research_tool_extension_snapshot"]["snapshot_hash"]
    manifest = first["research_tool_contract_pack_manifest"]
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["schema_count"] == 86
    assert manifest["expected_handler_count"] == 34


def test_manifest_input_order_does_not_change_snapshot():
    payload = snapshot_inputs(); expected = build_extension_snapshot(payload)
    reordered = deepcopy(payload)
    reordered["schema_bundle_manifest"]["entries"].reverse()
    reordered["extension_config_manifest"]["files"].reverse()
    assert build_extension_snapshot(reordered) == expected


def test_major_contract_version_is_rejected():
    payload = snapshot_inputs()
    payload["canonical_research_tool_catalog"]["contract_version"] = "2.0.0"
    with pytest.raises(ResearchToolContractError):
        build_extension_snapshot(payload)


def test_absolute_and_parent_paths_are_rejected():
    for path in ("/tmp/schema.json", "../schema.json", "C:/schema.json"):
        with pytest.raises(ValidationError):
            ContractPackFile(relative_path=path, kind="CONFIG", sha256="0" * 64, size_bytes=1)
