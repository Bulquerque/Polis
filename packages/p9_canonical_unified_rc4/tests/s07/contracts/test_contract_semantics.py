from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    ConsumerReceipt,
    EvidenceClass,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.m08_reality_gap import (
    ExecutionStage,
    StageExecutionRecord,
)

from tests.s07.conftest import h

pytestmark = pytest.mark.contract


def test_non_utc_clock_rejected():
    from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import ArtifactReference

    with pytest.raises(ValidationError, match="UTC"):
        ArtifactReference(
            artifact_id="a",
            artifact_type="x",
            artifact_schema_name="x",
            artifact_schema_version="1.0.0",
            artifact_schema_sha256=h("schema"),
            content_sha256=h("content"),
            producer_module_id="P9.S1.M01",
            run_id="r",
            cycle_id="c",
            available_at=datetime.now(timezone(timedelta(hours=3))),
            uri="artifact://a",
        )


def test_consumer_receipt_requires_disjoint_partition():
    with pytest.raises(ValidationError, match="disjoint"):
        ConsumerReceipt(
            consumer_module_id="P9.S7.M01",
            source_contract_name="P9_FOUNDATION_EXPERIMENT_BUNDLE_V1",
            source_contract_version="1.0.0",
            source_bundle_sha256=h("bundle"),
            input_ref_ids=("a",),
            accepted_ref_ids=("a",),
            rejected_ref_ids=("a",),
            reason_codes=("P9_TEST",),
        )


def test_live_stage_requires_factual_evidence(base_time):
    with pytest.raises(ValidationError, match="factual"):
        StageExecutionRecord(
            decision_id="d",
            cohort_id="c",
            policy_id="p",
            instrument_id="ABC",
            horizon_id="1d",
            stage=ExecutionStage.LIVE,
            decision_time=base_time,
            target_quantity=1.0,
            order_quantity=1.0,
            fill_quantity=1.0,
            benchmark_price=100.0,
            average_fill_price=100.0,
            fees=0.0,
            margin_used=0.0,
            pnl=0.0,
            evidence_class=EvidenceClass.MODEL_BASED_COUNTERFACTUAL,
        )
