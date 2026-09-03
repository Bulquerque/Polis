from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant_pipeline.phase_05_underlying_forecasts import ExecutionMode, PhaseRunner
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_base import V2ArtifactIdentity
from quant_pipeline.phase_05_underlying_forecasts.errors import DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.services.downstream import scenario_values_and_probabilities
from quant_pipeline.phase_05_underlying_forecasts.subphases import s1

from .fixtures import build_fixture
from .test_full_pipeline import _context, offline_requests, publication_requests, runtime_requests


def _complete_pipeline(tmp_path: Path):
    fixture = build_fixture()
    offline = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.OFFLINE_TRAINING)).run(offline_requests(fixture))
    runtime = PhaseRunner(_context(tmp_path, fixture, ExecutionMode.RUNTIME_INFERENCE)).run(
        runtime_requests(), initial_artifacts=offline.artifacts,
    )
    publication_context = _context(tmp_path, fixture, ExecutionMode.PUBLICATION)
    publication = PhaseRunner(publication_context).run(
        publication_requests(), initial_artifacts=runtime.artifacts,
    )
    return publication_context, publication


@pytest.fixture(scope="module")
def complete_pipeline(tmp_path_factory: pytest.TempPathFactory):
    """Build the expensive three-mode publication once for this module."""
    return _complete_pipeline(tmp_path_factory.mktemp("rc34_complete_pipeline"))


def test_rc34_v2_identity_rejects_future_publication_clock():
    decision = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        V2ArtifactIdentity(
            artifact_id="a", artifact_sha256="0" * 64, producer_module_id="P5.S9.M05",
            run_id="r", cycle_id="c", decision_time=decision,
            created_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc), lineage_id="l",
        )


def test_rc34_feedback_missing_authority_is_rejected():
    with pytest.raises(DataQualityError):
        s1.m04({"resolver_feedback_report": {"records": []}}, current_cycle_id="cycle-2")


def test_rc34_explicit_scenario_requires_probability():
    with pytest.raises(DataQualityError):
        scenario_values_and_probabilities({"scenarios": [{"value": 0.1}]})


def test_rc34_manifest_separates_native_and_extended_capabilities(complete_pipeline):
    context, publication = complete_pipeline
    manifest = context.artifact_store.read(publication.artifacts["phase6_strategy_scenario_manifest"])
    assert manifest["scenario_capability"] == "LIMITED"
    assert manifest["ambiguity_capability"] == "UNAVAILABLE"
    assert manifest["extended_scenario_path_capability"] == "AVAILABLE"
    assert manifest["extended_ambiguity_capability"] == "AVAILABLE"
    assert manifest["producer_contract_version"] == "P5-P6-V2"
    assert manifest["handoff_mode"] == "DEGRADED_V2"
    assert manifest["published_artifacts"] == [
        "market_belief_state", "return_distributions", "volatility_distributions",
        "path_risk_forecasts", "scenario_paths", "ambiguity_sets", "dependence_states",
        "regime_ood_states", "forecast_confidence", "availability_report", "lineage_report",
    ]
    assert "p6_native_contract_version" not in manifest


def test_rc34_market_belief_envelope_is_p6_native_shape(complete_pipeline):
    context, publication = complete_pipeline
    output = context.artifact_store.read(publication.artifacts["phase5_output_handoff_manifest"])
    belief = output["embedded_v2_artifacts"]["market_belief_state"]
    assert belief["record_count"] == len(belief["records"])
    assert len(belief["content_sha256"]) == 64
    allowed = {
        "belief_state_id", "underlying_id", "decision_time", "horizon_days", "scenarios",
        "confidence", "regime_context", "ambiguity_set_id", "ambiguity_probabilities",
        "scenario_capability", "ambiguity_capability", "surface_capability", "source_artifact_id",
    }
    assert all(set(record) == allowed for record in belief["records"])
    decision_times = {record["decision_time"] for record in belief["records"]}
    assert decision_times == {belief["decision_time"]}


def test_rc34_missing_path_jump_stays_null(complete_pipeline):
    context, publication = complete_pipeline
    distributions = context.artifact_store.read(publication.artifacts["forecast_distribution_panel"])
    path_risk = distributions["path_risk_forecasts"]
    if path_risk.get("availability") == "UNAVAILABLE":
        assert path_risk["reason_code"] == "P5_TARGET_UNAVAILABLE"
        assert "records" not in path_risk
    else:
        records = path_risk["artifact"]["records"]
        assert records
        assert any(record["jump_probability"] is None for record in records)
        assert all(record["validity_status"] in {"VALID", "DEGRADED"} for record in records)


def test_rc34_partial_confidence_forces_abstention(complete_pipeline):
    context, publication = complete_pipeline
    confidence = context.artifact_store.read(publication.artifacts["forecast_confidence_panel"])
    assert confidence["records"]
    partial = [row for row in confidence["records"] if row["calibration_status"] == "PARTIALLY_CALIBRATED"]
    assert partial
    assert all(row["abstained"] for row in partial)
    assert any(row["ood_component"] is None for row in partial)


def test_rc34_availability_report_is_derived_fail_closed(complete_pipeline):
    context, publication = complete_pipeline
    output = context.artifact_store.read(publication.artifacts["phase5_output_handoff_manifest"])
    report = output["embedded_v2_artifacts"]["availability_report"]["content"]["records"]
    by_type = {row["artifact_type"]: row for row in report}
    assert by_type["path_risk_forecasts"]["availability"] == "UNAVAILABLE"
    assert by_type["volatility_distributions"]["availability"] == "UNAVAILABLE"
    assert by_type["scenario_paths"]["availability"] in {"AVAILABLE", "DEGRADED"}


def test_rc34_dependence_publication_requires_diagnostics():
    from quant_pipeline.phase_05_underlying_forecasts.services.v2_context_publication import (
        build_dependence_artifact,
    )

    result = build_dependence_artifact(
        {"records": [{
            "validated": True,
            "matrix": [[1.0]],
            "correlation_matrix": [[1.0]],
            "entities": ["AAA"],
            "diagnostics": {},
        }]},
        run_id="run", cycle_id="cycle",
        decision_time="2025-01-01T00:00:00Z",
        created_at="2025-01-01T00:00:00Z",
    )
    assert result["availability"] == "UNAVAILABLE"
    assert result["reason_code"] == "P5_COVARIANCE_UNSTABLE"


def _feedback_report(*, source_cycle_id="cycle-1", available_at="2025-01-02T00:00:00Z"):
    from quant_pipeline.phase_05_underlying_forecasts.boundary.models import canonical_sha256
    payload = {
        "schema_version": "P9-P5-FEEDBACK-V1",
        "feedback_route": "NEXT_CYCLE_ONLY",
        "source_phase": "P9",
        "source_run_id": "p9-run-1",
        "source_cycle_id": source_cycle_id,
        "promotion_status": "PROMOTED",
        "promotion_decision_id": "promotion-1",
        "created_at": "2025-01-01T23:59:00Z",
        "available_at": available_at,
        "records": [{
            "feedback_id": "feedback-1",
            "effect_type": "CHALLENGER_ELIGIBILITY",
            "effect_payload": {"eligible": True},
            "resolver_id": "resolver-1",
            "target_id": "return_1d",
            "horizon": "1D",
            "reason_code": "P9_PROMOTED_CHALLENGER",
            "lineage_id": "feedback-lineage-1",
        }],
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def test_rc34_feedback_contract_is_closed_and_content_addressed():
    report = _feedback_report()
    result = s1.m04(
        {"resolver_feedback_report": report},
        current_cycle_id="cycle-2",
        current_as_of_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    output = result.values[0]
    assert output["accepted_report_count"] == 1
    assert output["records"][0]["effect_payload"] == {"eligible": True}
    tampered = dict(report)
    tampered["unexpected_field"] = "forbidden"
    with pytest.raises(DataQualityError, match="closed P9-P5 feedback contract"):
        s1.m04({"resolver_feedback_report": tampered}, current_cycle_id="cycle-2")


def test_rc34_feedback_rejects_same_cycle_and_future_availability():
    with pytest.raises(DataQualityError, match="distinct prior"):
        s1.m04({"resolver_feedback_report": _feedback_report(source_cycle_id="cycle-2")}, current_cycle_id="cycle-2")
    with pytest.raises(DataQualityError, match="not available"):
        s1.m04(
            {"resolver_feedback_report": _feedback_report(available_at="2025-01-03T00:00:00Z")},
            current_cycle_id="cycle-2",
            current_as_of_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
