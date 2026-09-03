from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from quant_pipeline.phase_03_agents_rag_memory import s31_models

ROOT = Path(__file__).resolve().parents[2]


def test_all_semantic_schemas_are_valid_draft_2020_12():
    files = sorted((ROOT / "schemas" / "products" / "s31").glob("*.json"))
    assert len(files) == 10
    for path in files:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_output_models_are_strict_and_preserve_legacy_required_fields():
    bundle = s31_models.P9EvaluationEvidenceBundle.model_json_schema()
    handoff = s31_models.P9ContextLearningHandoffManifest.model_json_schema()
    assert bundle["additionalProperties"] is False
    assert handoff["additionalProperties"] is False
    assert {"schema_version", "items", "lineage_id"} <= set(bundle["required"])
    assert {"schema_version", "artifact_hashes", "lineage_id"} <= set(handoff["required"])


def test_output_semantic_json_schemas_are_strict():
    for name in (
        "p9_evaluation_evidence_bundle.semantic.schema.json",
        "p9_context_learning_handoff_manifest.semantic.schema.json",
    ):
        schema = json.loads(
            (ROOT / "schemas" / "products" / "s31" / name).read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert schema["required"]


def test_current_p9_contract_hashes_are_exact_and_s31_outputs_are_not_inputs():
    manifest = yaml.safe_load((ROOT / "contracts" / "products" / "S31_CURRENT_P9_CONTRACT_HASHES.yaml").read_text())
    for row in manifest["files"]:
        path = ROOT / row["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    current = yaml.safe_load((ROOT / "contracts" / "products" / "current_p9" / "INPUT_CONTRACTS.yaml").read_text())
    assert "p9_evaluation_evidence_bundle" not in current["required_inputs"]
    assert "p9_context_learning_handoff_manifest" not in current["required_inputs"]
    assert manifest["binding_status"] == "CONSUMER_NOT_YET_BOUND"


def test_module_contracts_are_canonical_and_implemented():
    names = (
        "p9_evaluation_evidence_bundle_builder",
        "p9_context_learning_handoff_builder",
    )
    for index, name in enumerate(names, start=1):
        path = ROOT / "modules" / f"P3_S31_M{index:02d}_{name}.yaml"
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert contract["module_id"] == f"P3.S31.M{index:02d}"
        assert contract["status"] == "implemented_qualified_internal"
        assert contract["implementation_status_policy"]["current"] == "IMPLEMENTED_QUALIFIED_INTERNAL"
