from __future__ import annotations

import copy

import pytest
import yaml

from quant_pipeline.phase_03_agents_rag_memory.foundation.governance.errors import S1ContractError
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S1_M01_phase2_handoff_contract_validator import run_module

from .test_p3_s2_temporal_authority import _s1


def test_p3_s1_m01_accepts_canonical_p2_handoff(root):
    payload, _ = _s1(root)
    result = run_module(payload)
    assert result["outputs"]["validated_phase2_handoff"]["validation_status"] == "READY"


def test_p3_handoff_schema_authority_targets_phase3_in_all_mirrors(root):
    for schema_name in ("context_handoff_manifest", "phase3_handoff_manifest"):
        schema_paths = (
            root / f"schemas/{schema_name}.schema.yaml",
            root / f"assets/schemas/{schema_name}.schema.yaml",
            root / f"src/quant_pipeline/phase_03_agents_rag_memory/assets/schemas/{schema_name}.schema.yaml",
        )
        documents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in schema_paths]
        assert {document["phase"] for document in documents} == {"phase_03_agents_rag_memory"}
        assert documents[0] == documents[1] == documents[2]


def test_p3_s1_m01_preserves_p2_identity_and_cardinality(root):
    payload, _ = _s1(root)
    output = run_module(payload)["outputs"]["validated_phase2_handoff"]
    references = {row["artifact_name"]: row for row in output["artifacts"]}

    for artifact_name in (
        "clean_context_source_panel",
        "clean_document_panel",
        "clean_event_reference_panel",
        "source_quality_panel",
    ):
        source = payload[artifact_name]
        reference = references[artifact_name]
        assert reference["artifact_id"] == source["artifact_id"]
        assert reference["lineage_id"] == source["lineage_id"]
        assert reference["row_count"] == len(source["records"])

    assert output["cross_artifact_checks"]["input_immutability_preserved"] is True


def test_p3_s1_m01_rejects_manifest_hash_mismatch(root):
    payload, _ = _s1(root)
    tampered = copy.deepcopy(payload)
    tampered["phase3_handoff_manifest"]["artifact_refs"][0]["content_hash"] = "0" * 64

    with pytest.raises(S1ContractError, match="HASH_MISMATCH"):
        run_module(tampered)
