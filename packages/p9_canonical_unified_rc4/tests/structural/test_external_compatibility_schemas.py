from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "src/quant_pipeline/phase_09/compatibility/generated_schemas"


def test_external_schema_snapshots_are_valid_and_fingerprint_bound() -> None:
    matrix = json.loads((ROOT / "registries/cross_phase_compatibility_matrix.json").read_text())
    fingerprints = {row["phase_id"]: row["fingerprint_sha256"] for row in matrix["entries"]}
    expected = {
        "P8NativeP9EvaluationHandoff.schema.json": "P8",
        "P8NativeStatefulEvidenceBundle.schema.json": "P8",
        "P9ToP8PromotedFeedbackV1.schema.json": "P8",
        "P3P9EvaluationEvidenceBundle.schema.json": "P3",
        "P3P9ContextLearningHandoffManifest.schema.json": "P3",
    }
    for filename, phase_id in expected.items():
        schema = json.loads((SCHEMAS / filename).read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["x-qualified-source-phase"] == phase_id
        assert schema["x-qualified-source-fingerprint"] == fingerprints[phase_id]
        assert schema["x-authority"] == "external-source-snapshot-not-p9-authority"


def test_packaged_matrix_matches_registry_matrix() -> None:
    registry = json.loads((ROOT / "registries/cross_phase_compatibility_matrix.json").read_text())
    packaged = json.loads(
        (
            ROOT
            / "src/quant_pipeline/phase_09/compatibility/resources/cross_phase_compatibility_matrix.json"
        ).read_text()
    )
    assert packaged == registry
