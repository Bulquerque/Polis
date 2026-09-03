from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S4_M01_scoring_policy_head_binding_compiler import run_module

from tests.tournament.tests.s4.factories import DECISION_TIME, execution_config, future_policy_bundle, make_bundle, replace_artifact_records


def test_policy_available_after_decision_is_rejected():
    with pytest.raises(TemporalViolation) as exc:
        run_module(future_policy_bundle(), execution_config())
    assert exc.value.code == "P7_S4_POLICY_AVAILABLE_AFTER_DECISION"


def test_metric_available_after_decision_is_rejected():
    bundle = make_bundle()
    records = bundle["comparable_candidate_metric_panel"]["records"]
    records[0]["source_available_at"] = (DECISION_TIME + timedelta(seconds=1)).isoformat()
    bundle = replace_artifact_records(bundle, "comparable_candidate_metric_panel", records)
    config = execution_config()
    config["strict_hash_validation"] = False
    with pytest.raises(TemporalViolation) as exc:
        run_module(bundle, config)
    assert exc.value.code == "P7_S4_METRIC_AVAILABLE_AFTER_DECISION"
