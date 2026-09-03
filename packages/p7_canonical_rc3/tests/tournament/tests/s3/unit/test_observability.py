from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.observability.events import DebugEvent

from tests.tournament.tests.s3.factories import DECISION_TIME


def test_debug_event_serializes_identifiers_and_counts():
    event = DebugEvent(
        event_name="module_completed",
        timestamp=DECISION_TIME,
        run_id="run-1",
        cycle_id="cycle-1",
        module_id="P7.S3.M01",
        status="PASS",
        input_artifact_ids=("input-1",),
        output_artifact_ids=("output-1",),
        counts={"records": 3},
        details={"policy_id": "policy-v1"},
    )
    payload = event.to_dict()
    assert payload["timestamp"] == DECISION_TIME.isoformat()
    assert payload["counts"] == {"records": 3}
