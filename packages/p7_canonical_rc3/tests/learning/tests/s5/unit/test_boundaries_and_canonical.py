from __future__ import annotations

import math
from datetime import datetime

import pytest

from quant_pipeline.phase_07_strategy_tournament.learning.boundary import ArtifactEnvelope, parse_artifact, parse_context
from quant_pipeline.phase_07_strategy_tournament.learning.domain.canonical import canonical_json, digest, parse_utc, sorted_records
from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7S5Error


def test_artifact_integrity_and_contract_failures(input_bundle, config):
    artifact = input_bundle["metric_semantics_registry"]
    broken = dict(artifact, record_count=2)
    with pytest.raises(P7S5Error, match="P7_LTR_ARTIFACT_COUNT_MISMATCH"):
        parse_artifact(broken, name="metric_semantics_registry")
    broken = dict(artifact, content_sha256="0" * 64)
    with pytest.raises(P7S5Error, match="P7_LTR_ARTIFACT_HASH_MISMATCH"):
        parse_artifact(broken, name="metric_semantics_registry")
    with pytest.raises(P7S5Error, match="P7_LTR_CONTRACT_INVALID"):
        parse_artifact([], name="metric_semantics_registry")
    with pytest.raises(P7S5Error, match="P7_LTR_CONTRACT_INVALID"):
        parse_artifact(artifact, name="wrong_name")
    with pytest.raises(P7S5Error, match="P7_LTR_CONTRACT_INVALID"):
        parse_context({})
    bad = {**config, "context": {**config["context"], "decision_time": "not-a-date"}}
    with pytest.raises(P7S5Error, match="P7_LTR_CONTRACT_INVALID"):
        parse_context(bad)


def test_timezone_and_canonical_guards():
    with pytest.raises(ValueError, match="timezone-aware"):
        ArtifactEnvelope(
            artifact_id="a", artifact_name="x", schema_version="1", producer_phase="p",
            producer_module_id="m", pipeline_version="v", run_id="r", cycle_id="c",
            decision_time=datetime(2025, 1, 1), available_at=datetime(2025, 1, 1),
            created_at=datetime(2025, 1, 1), lineage_id="l", content_sha256=digest([]),
            record_count=0, records=(),
        )
    for value in (1, "bad", "2025-01-01T00:00:00"):
        with pytest.raises(P7S5Error, match="P7_LTR_CONTRACT_INVALID"):
            parse_utc(value, field="time")
    with pytest.raises(P7S5Error, match="P7_LTR_NON_FINITE_VALUE"):
        canonical_json({"x": math.inf})
    assert sorted_records([{"x": 2}, {"x": 1}], ("x",)) == [{"x": 1}, {"x": 2}]
