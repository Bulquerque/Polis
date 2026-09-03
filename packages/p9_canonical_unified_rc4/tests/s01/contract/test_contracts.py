from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.contracts.artifacts import ArtifactReference
from quant_pipeline.phase_09.contracts.base import Availability, ModuleStatus
from quant_pipeline.phase_09.contracts.handoff import CandidateTerminalCounts
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    ModuleExecutionReceiptPayload,
    SubphaseExecutionReceiptPayload,
)

HASH = "0" * 64


def test_artifact_reference_rejects_non_utc() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            artifact_id="a",
            artifact_type="x",
            schema_name="x",
            artifact_schema_version="1.0.0",
            schema_sha256=HASH,
            content_sha256=HASH,
            producer_module_id="P8.S1.M01",
            run_id="r",
            cycle_id="c",
            backtest_id="b",
            available_at=datetime.now(timezone(timedelta(hours=3))),
            computed_at=datetime.now(timezone(timedelta(hours=3))),
            location="mem://a",
            availability=Availability.AVAILABLE,
            record_count=1,
        )


def test_artifact_reference_rejects_clock_reversal() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ArtifactReference(
            artifact_id="a",
            artifact_type="x",
            schema_name="x",
            artifact_schema_version="1.0.0",
            schema_sha256=HASH,
            content_sha256=HASH,
            producer_module_id="P8.S1.M01",
            run_id="r",
            cycle_id="c",
            backtest_id="b",
            available_at=now,
            computed_at=now - timedelta(seconds=1),
            location="mem://a",
            availability=Availability.AVAILABLE,
            record_count=1,
        )


def test_candidate_counts_enforce_conservation() -> None:
    with pytest.raises(ValidationError):
        CandidateTerminalCounts(
            received=2,
            selected=1,
            rejected=0,
            no_action=0,
            execution_failed=0,
            other_terminal=0,
        )


def test_receipt_rejects_end_before_start() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ModuleExecutionReceiptPayload(
            module_id="P9.S1.M01",
            status=ModuleStatus.SUCCESS,
            started_at=now,
            completed_at=now - timedelta(seconds=1),
            implementation_sha256=HASH,
            policy_sha256=HASH,
        )


def test_subphase_receipt_requires_exact_module_coverage() -> None:
    now = datetime.now(UTC)
    payload = ModuleExecutionReceiptPayload(
        module_id="P9.S1.M01",
        status=ModuleStatus.SUCCESS,
        started_at=now,
        completed_at=now,
        implementation_sha256=HASH,
        policy_sha256=HASH,
    )
    receipt = ModuleExecutionReceipt(
        payload=payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )
    with pytest.raises(ValidationError):
        SubphaseExecutionReceiptPayload(
            subphase_id="P9.S1",
            expected_module_ids=("P9.S1.M01", "P9.S1.M02"),
            module_receipts=(receipt,),
            status=ModuleStatus.SUCCESS,
        )


def test_decimal_is_finite() -> None:
    now = datetime.now(UTC)
    from quant_pipeline.phase_09.contracts.replay import ReplayState

    with pytest.raises(ValidationError):
        ReplayState(as_of=now, cash=Decimal("NaN"))
