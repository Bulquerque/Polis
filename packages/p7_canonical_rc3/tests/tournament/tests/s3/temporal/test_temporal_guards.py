from __future__ import annotations

from datetime import timedelta

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import IntegrityViolation, TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S3_M01_candidate_metric_semantics_compiler import run_module

from tests.tournament.tests.s3.factories import DECISION_TIME, execution_config, make_bundle


def test_hash_mismatch_is_rejected_before_processing():
    bundle = make_bundle()
    bundle["candidate_metric_source_panel"]["content_sha256"] = "0" * 64
    with pytest.raises(IntegrityViolation) as exc_info:
        run_module(bundle, execution_config())
    assert exc_info.value.code == "P7_S3_CONTENT_HASH_MISMATCH"


def test_future_metric_availability_is_rejected():
    bundle = make_bundle()
    bundle["candidate_metric_source_panel"]["records"][0]["available_at"] = (
        DECISION_TIME + timedelta(seconds=1)
    ).isoformat()
    config = execution_config()
    config["strict_hash_validation"] = False
    with pytest.raises(TemporalViolation) as exc_info:
        run_module(bundle, config)
    assert exc_info.value.code in {
        "P7_S3_METRIC_AVAILABLE_AFTER_DECISION",
        "P7_S3_ARTIFACT_AVAILABLE_AFTER_DECISION",
    }
