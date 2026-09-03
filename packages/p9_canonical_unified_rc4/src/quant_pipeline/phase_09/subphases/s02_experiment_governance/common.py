from __future__ import annotations

import hashlib
from pathlib import Path

from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    ModuleExecutionReceiptPayload,
)


def build_integrity(payload: object) -> IntegrityEnvelope:
    return IntegrityEnvelope(payload_sha256=payload_sha256(payload))


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_module_receipt(
    *,
    module_id: str,
    status: ModuleStatus,
    started_at,
    completed_at,
    input_artifact_ids: tuple[str, ...] = (),
    output_artifact_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    implementation_sha256: str,
    policy_sha256: str,
) -> ModuleExecutionReceipt:
    payload = ModuleExecutionReceiptPayload(
        module_id=module_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        input_artifact_ids=input_artifact_ids,
        output_artifact_ids=output_artifact_ids,
        reason_codes=reason_codes,
        limitations=limitations,
        implementation_sha256=implementation_sha256,
        policy_sha256=policy_sha256,
    )
    return ModuleExecutionReceipt(payload=payload, integrity=build_integrity(payload))
