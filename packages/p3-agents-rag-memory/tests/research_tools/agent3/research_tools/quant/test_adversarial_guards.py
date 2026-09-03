from __future__ import annotations

import pytest
from datetime import UTC, datetime

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.evidence import (
    evidence_from_record,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.event_window import (
    event_time_from_records,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.qualification import (
    build_operation_mode_qualification,
    combine_quant_tool_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.handlers import (
    build_dependence_entropy_bundle,
    build_event_scenario_bundle,
    build_return_risk_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.model_base import (
    ExtensionLineage,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.ports import (
    TemporalVisibilityError,
    enforce_visibility,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.quant.models import (
    QuantMode,
)


def test_qualification_rejects_unproven_pit_status() -> None:
    rows = ({
        "record_id": "unproven-1",
        "source_id": "real-source",
        "source_artifact_id": "sha256:" + "a" * 64,
        "available_at": "2024-01-09T16:00:00Z",
        "observation_time": "2024-01-09T16:00:00Z",
        "pit_status": "DATE_LEVEL_PIT_UNPROVEN",
    },)
    with pytest.raises(TemporalVisibilityError, match="unproven status"):
        enforce_visibility(
            rows,
            decision_time=datetime(2024, 1, 10, tzinfo=UTC),
            qualification_mode=True,
        )


def test_future_observation_is_rejected_even_when_available_at_is_old() -> None:
    rows = ({
        "record_id": "future-observation",
        "source_id": "real-source",
        "source_artifact_id": "sha256:" + "b" * 64,
        "available_at": "2024-01-01T00:00:00Z",
        "observation_time": "2030-01-01T00:00:00Z",
        "pit_status": "VALID_DAILY_POLICY",
    },)
    visible, rejected = enforce_visibility(
        rows,
        decision_time=datetime(2024, 1, 10, tzinfo=UTC),
        qualification_mode=True,
    )
    assert visible == ()
    assert rejected == 1


def test_source_artifact_id_is_preserved_as_p2_artifact_provenance() -> None:
    reference = evidence_from_record(
        {
            "record_id": "real-1",
            "source_id": "real-source",
            "source_artifact_id": "sha256:" + "c" * 64,
            "available_at": "2024-01-09T16:00:00Z",
        },
        index=0,
    )
    assert reference.p2_artifact_id == "sha256:" + "c" * 64
    assert "unknown-artifact" not in reference.evidence_id


def test_event_time_adapter_is_explicit_and_fail_closed() -> None:
    observed_time, observed = event_time_from_records(
        [{"event_id": "E1", "observed_at": "2024-01-03T12:00:00Z"}],
        event_id="E1",
    )
    assert observed_time.isoformat() == "2024-01-03T12:00:00+00:00"
    assert observed["event_time_source"] == "observed_at"
    reference_time, referenced = event_time_from_records(
        [{"event_id": "E2", "reference_date": "2024-01-03"}],
        event_id="E2",
    )
    assert reference_time.isoformat() == "2024-01-03T00:00:00+00:00"
    assert referenced["event_time_precision"] == "DAILY"
    with pytest.raises(ValueError, match="no approved"):
        event_time_from_records([{"event_id": "E3"}], event_id="E3")


def test_m04_blocks_empty_or_status_only_test_evidence() -> None:
    lineage = ExtensionLineage(
        lineage_id="s39-test-lineage",
        producer_module_id="P3.S39.M04",
    )
    bundles = (
        build_return_risk_bundle(lineage),
        build_dependence_entropy_bundle(lineage),
        build_event_scenario_bundle(lineage),
    )
    matrix = build_operation_mode_qualification(
        tool_bundle=combine_quant_tool_bundle(bundles=bundles, lineage=lineage),
        lineage=lineage,
        contract_report={"status": "PASS", "passed": 0},
        property_report={"status": "PASS", "passed": 0},
        leakage_report={"status": "PASS", "passed": 0},
    )
    assert {record.status.value for record in matrix.records} == {"BLOCKED_UPSTREAM"}
    assert all(
        any("EXECUTED_EMPTY" in code for code in record.reason_codes)
        for record in matrix.records
    )
