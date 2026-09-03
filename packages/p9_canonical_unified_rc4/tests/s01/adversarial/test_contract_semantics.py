from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.contracts.artifacts import ArtifactAbsenceState, ArtifactSlot
from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.receipts import (
    ConsumerReceiptPayload,
    ModuleExecutionReceipt,
    ModuleExecutionReceiptPayload,
    SubphaseExecutionReceiptPayload,
)

H = "0" * 64
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _receipt(module_id: str, status: ModuleStatus, *, reasons: tuple[str, ...] = ()):
    payload = ModuleExecutionReceiptPayload(
        module_id=module_id,
        status=status,
        started_at=NOW,
        completed_at=NOW,
        reason_codes=reasons,
        implementation_sha256=H,
        policy_sha256=H,
    )
    return ModuleExecutionReceipt(
        payload=payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )


def test_artifact_slot_requires_exactly_one_state() -> None:
    with pytest.raises(ValidationError):
        ArtifactSlot(role="x")
    with pytest.raises(ValidationError):
        ArtifactSlot(
            role="x",
            absence_state=ArtifactAbsenceState.NOT_PRODUCED,
            reason_codes=(),
        )


def test_module_receipt_rejects_reverse_time() -> None:
    with pytest.raises(ValidationError):
        ModuleExecutionReceiptPayload(
            module_id="P9.S1.M01",
            status=ModuleStatus.SUCCESS,
            started_at=NOW,
            completed_at=NOW - timedelta(seconds=1),
            implementation_sha256=H,
            policy_sha256=H,
        )


def test_success_receipt_rejects_blocking_reason_codes() -> None:
    with pytest.raises(ValidationError):
        ModuleExecutionReceiptPayload(
            module_id="P9.S1.M01",
            status=ModuleStatus.SUCCESS,
            started_at=NOW,
            completed_at=NOW,
            reason_codes=("P9_TEST_BLOCKING",),
            implementation_sha256=H,
            policy_sha256=H,
        )


def test_subphase_rejects_failed_child_labeled_success() -> None:
    child = _receipt("P9.S1.M01", ModuleStatus.FAILED, reasons=("P9_TEST_FAILED",))
    with pytest.raises(ValidationError):
        SubphaseExecutionReceiptPayload(
            subphase_id="P9.S1",
            expected_module_ids=("P9.S1.M01",),
            module_receipts=(child,),
            status=ModuleStatus.SUCCESS,
        )


def test_consumer_dispositions_are_disjoint() -> None:
    with pytest.raises(ValidationError):
        ConsumerReceiptPayload(
            consumer_module_id="P9.S1.M01",
            source_contract_name="source",
            source_contract_version="1.0.0",
            source_payload_sha256=H,
            accepted_artifact_ids=("a",),
            rejected_artifact_ids=("a",),
            reason_codes=("P9_TEST_REJECTED",),
        )


def test_module_receipt_rejects_tampered_integrity() -> None:
    payload = ModuleExecutionReceiptPayload(
        module_id="P9.S1.M01",
        status=ModuleStatus.SUCCESS,
        started_at=NOW,
        completed_at=NOW,
        implementation_sha256=H,
        policy_sha256=H,
    )
    with pytest.raises(ValidationError):
        ModuleExecutionReceipt(
            payload=payload,
            integrity=IntegrityEnvelope(payload_sha256=H),
        )
