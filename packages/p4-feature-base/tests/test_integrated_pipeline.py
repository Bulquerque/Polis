from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from quant_pipeline.phase_04_feature_base.integrated_runner import run_integrated_phase
from quant_pipeline.phase_04_feature_base.runtime.canonical import p2_legacy_digest
from quant_pipeline.phase_04_feature_base.temporal.errors import TemporalContractError

from phase_04_extracted.phase_04_feature_base_agent_package_RC4_1.tests.full_pipeline_fixture import build_full_inputs


@pytest.fixture(scope="module")
def full_result():
    inputs, context = build_full_inputs(70)
    return run_integrated_phase(
        inputs,
        context,
        encoder_requested=False,
        allow_partial=False,
    )


def _record_count(artifact) -> int:
    if hasattr(artifact, "record_count"):
        return int(artifact.record_count)
    return len(artifact.get("records", []))


def test_full_s1_to_s9_pipeline(full_result) -> None:
    assert full_result["status"] == "PRODUCED"
    assert set(full_result["subphases"]) == {f"P4.S{i}" for i in range(1, 10)}
    assert full_result["integration_report"]["a1_to_a2_adapter"] == "PASS"
    assert full_result["integration_report"]["a2_to_a3_adapter"] == "PASS"
    assert full_result["integration_report"]["horizon_timestamp_count"] == 70
    assert _record_count(full_result["outputs"]["canonical_observation_panel"]) > 1_000
    assert _record_count(full_result["outputs"]["horizon_feature_panel"]) > 1_000
    assert _record_count(full_result["outputs"]["underlying_feature_matrix_selected"]) > 0
    assert _record_count(full_result["outputs"]["underlying_feature_factors_pca"]) > 0


def test_historical_decision_times_are_preserved(full_result) -> None:
    records = full_result["outputs"]["canonical_observation_panel"]["records"]
    decision_times = {record["decision_time"] for record in records}
    # 70 market decision points plus the final hypothesis-registry decision point.
    assert len(decision_times) >= 70
    assert all(record["available_at"] <= record["decision_time"] for record in records)


def test_pca_and_handoff_have_only_finite_values(full_result) -> None:
    outputs = full_result["outputs"]
    pca = outputs["underlying_feature_factors_pca"]
    for record in pca.records:
        for value in record.values() if isinstance(record, dict) else ():
            if isinstance(value, float):
                assert math.isfinite(value)
    decision = outputs["p4_quality_gate_decision"]
    handoff = outputs["phase5_feature_handoff_manifest"]
    assert str(decision.execution_status) == "PRODUCED"
    assert str(handoff.execution_status) == "PRODUCED"
    assert decision.records[-1]["decision"] == "PASS"
    assert handoff.metadata["completeness_status"] == "COMPLETE"
    coverage = handoff.metadata["family_coverage"]
    assert coverage["missing_required_family_ids"] == []
    assert set(coverage["required_family_ids"]) == {f"F{index:02d}" for index in range(1, 11)}


def test_p4_to_p5_handoff_and_receipt_match_canonical_schemas(full_result) -> None:
    package_root = Path(__file__).resolve().parents[1]
    outputs = full_result["outputs"]
    schema_paths = {
        "phase5_feature_handoff_manifest": package_root
        / "schemas"
        / "s9"
        / "phase5_feature_handoff_manifest.schema.yaml",
        "p4_to_p5_integration_receipt": package_root
        / "schemas"
        / "s9"
        / "p4_to_p5_integration_receipt.schema.yaml",
    }
    for name, schema_path in schema_paths.items():
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(outputs[name].model_dump(mode="json"))

    handoff = outputs["phase5_feature_handoff_manifest"]
    receipt = outputs["p4_to_p5_integration_receipt"]
    receipt_record = receipt.records[0]
    assert receipt_record["manifest_id"] == handoff.artifact_id
    assert receipt_record["manifest_hash"] == handoff.content_hash
    assert receipt_record["receipt_status"] == "SKIPPED_NOT_AVAILABLE"
    assert receipt.execution_status == "SKIPPED_NOT_AVAILABLE"


def test_raw_matrix_is_materialized_and_distinct_from_interpretable(full_result) -> None:
    outputs = full_result["outputs"]
    raw = outputs["underlying_feature_matrix_raw"]
    interpretable = outputs["underlying_feature_matrix_interpretable"]
    assert raw.records
    assert raw.metadata["view_semantics"] == "raw_transformed_inputs_before_normalization"
    assert raw.alias_of is None
    assert raw.metadata["paired_interpretable_artifact_id"] == interpretable.artifact_id
    assert raw.grain == interpretable.grain
    observed_rows = [
        row for row in raw.records if any(value is not None for value in row["values"].values())
    ]
    assert observed_rows
    assert all(row["values"] == row["raw_values"] for row in observed_rows)


def test_selected_matrix_preserves_point_in_time_availability(full_result) -> None:
    records = full_result["outputs"]["underlying_feature_matrix_selected"].records
    assert records
    for row in records:
        assert row["available_at"]
        assert row["available_at"] <= row["decision_time"]


def test_representation_outputs_preserve_point_in_time_availability(full_result) -> None:
    from datetime import datetime

    for name in ("underlying_feature_factors_pca", "underlying_feature_embeddings"):
        for row in full_result["outputs"][name].records:
            assert row["available_at"]
            available = datetime.fromisoformat(str(row["available_at"]).replace("Z", "+00:00"))
            decision = datetime.fromisoformat(str(row["decision_time"]).replace("Z", "+00:00"))
            assert available <= decision


def test_short_history_returns_controlled_partial() -> None:
    inputs, context = build_full_inputs(8)
    result = run_integrated_phase(inputs, context, allow_partial=True)
    assert result["status"] == "DEGRADED_INSUFFICIENT_HISTORY"
    assert result["integration_report"]["a1_to_a2_adapter"] == "PASS"
    assert result["integration_report"]["a2_to_a3_adapter"] == "NOT_RUN"
    assert set(result["subphases"]) == {f"P4.S{i}" for i in range(1, 7)}


def test_record_decision_time_after_cutoff_is_rejected() -> None:
    inputs, context = build_full_inputs(8)
    inputs["clean_underlying_panel"]["records"][0]["decision_time"] = "2099-01-01T00:00:00+00:00"
    new_hash = p2_legacy_digest(inputs["clean_underlying_panel"])
    for reference in inputs["phase4_handoff_manifest"]["artifact_refs"]:
        if reference["artifact_name"] == "clean_underlying_panel":
            reference["content_hash"] = new_hash
    with pytest.raises(TemporalContractError):
        run_integrated_phase(inputs, context, allow_partial=True)


def test_derived_atomic_feature_is_compiled_to_real_observer(full_result) -> None:
    records = full_result["outputs"]["risk_tail_atomic_panel"]["records"]
    match = [row for row in records if row["feature_id"] == "risk.realized_volatility_5"]
    assert match
    assert {row["observer_id"] for row in match} == {"risk.realized_volatility"}
    assert {row["attributes"]["window"] for row in match} == {5}


def test_composite_features_preserve_temporal_availability(full_result) -> None:
    from datetime import datetime

    records = full_result["outputs"]["horizon_feature_panel"]["records"]
    composites = [row for row in records if row.get("feature_kind") in {"CONFLICT", "INTERACTION"}]
    assert composites
    for row in composites:
        available = datetime.fromisoformat(str(row["available_at"]).replace("Z", "+00:00"))
        decision = datetime.fromisoformat(str(row["decision_time"]).replace("Z", "+00:00"))
        assert available <= decision
        expected_age = (decision - available).total_seconds()
        assert abs(float(row["information_age_seconds"]) - expected_age) < 1e-6


def test_all_fit_state_payloads_are_finite(full_result) -> None:
    def assert_finite(value) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for item in value.values():
                assert_finite(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                assert_finite(item)

    for name in (
        "feature_transform_state_manifest",
        "pca_fit_state_manifest",
        "encoder_fit_state_manifest",
    ):
        artifact = full_result["outputs"][name]
        assert_finite(list(artifact.records))
