from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from quant_pipeline.phase_07_strategy_tournament.foundation.runner import run_subphase_s1

ROOT = Path(__file__).resolve().parents[1]


def _schema(relative):
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def test_all_schemas_are_valid_draft_2020_12():
    for path in (ROOT / "schemas").rglob("*.schema.yaml"):
        Draft202012Validator.check_schema(yaml.safe_load(path.read_text(encoding="utf-8")))


def test_output_envelopes_and_candidate_record_validate(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    result = run_subphase_s1(
        phase6_manifest=manifest,
        phase6_artifacts=artifacts,
        module_config=module_config,
    )
    envelope_validator = Draft202012Validator(_schema("schemas/artifact_envelope.schema.yaml"))
    candidate_validator = Draft202012Validator(
        _schema("schemas/records/validated_strategy_candidate_record.schema.yaml")
    )
    for module in ("P7.S1.M01", "P7.S1.M02", "P7.S1.M03", "P7.S1.M04"):
        for artifact in result[module]["outputs"].values():
            envelope_validator.validate(artifact)
    for record in result["outputs"]["temporally_safe_candidate_bundle"]["records"]:
        candidate_validator.validate(record)
