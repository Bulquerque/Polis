"""Authority-aware verification for signed cross-phase receipts."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from .hashing import verify_mapping_ed25519
from .models import Authority, PublicKeyRecord, ReceiptType, SignedReceipt

EXPECTED_ARTIFACTS: dict[ReceiptType, set[str]] = {
    ReceiptType.PLATFORM_QUALIFICATION: {"runtime_qualification_bundle"},
    ReceiptType.P2_HANDOFF: {"phase3_handoff_manifest"},
    ReceiptType.P4_CONSUMPTION: {
        "social_feature_panel",
        "evidence_tag_panel",
        "agent_disagreement_panel",
        "context_memory_feature_panel",
        "hypothesis_registry",
        "phase4_social_handoff_manifest",
    },
    ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION: {"variable_evolution_input_manifest"},
    ReceiptType.P9_EVALUATION: {
        "p9_evaluation_evidence_bundle",
        "p9_context_learning_handoff_manifest",
        "belief_outcome_commitment_log",
    },
    ReceiptType.P9_FEEDBACK: {
        "p9_belief_outcome_feedback_package",
        "phase3_learning_feedback_handoff_manifest",
    },
    ReceiptType.N_PLUS_1_FEEDBACK: {"active_belief_feedback_bundle"},
    ReceiptType.CHECKPOINT_RELOAD: {"cycle_state_snapshot_out"},
    ReceiptType.MODULE_TRACE: {"module_execution_trace"},
    ReceiptType.FOLD_CHECKPOINT: {"fold_checkpoint"},
}

EXPECTED_AUTHORITIES: dict[ReceiptType, Authority] = {
    ReceiptType.PLATFORM_QUALIFICATION: Authority.OPERATIONS,
    ReceiptType.P2_HANDOFF: Authority.P2,
    ReceiptType.P4_CONSUMPTION: Authority.P4,
    ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION: Authority.P4,
    ReceiptType.P9_EVALUATION: Authority.P9,
    ReceiptType.P9_FEEDBACK: Authority.P9,
    ReceiptType.N_PLUS_1_FEEDBACK: Authority.P3_RUNTIME,
    ReceiptType.CHECKPOINT_RELOAD: Authority.P3_RUNTIME,
    ReceiptType.MODULE_TRACE: Authority.P3_RUNTIME,
    ReceiptType.FOLD_CHECKPOINT: Authority.P3_RUNTIME,
}


def verify_receipt(
    receipt: SignedReceipt,
    keyring: Mapping[str, PublicKeyRecord],
    *,
    release_id: str,
    release_sha256: str,
) -> list[str]:
    errors: list[str] = []
    key = keyring.get(receipt.key_id)
    if key is None:
        return [f"unknown key_id: {receipt.key_id}"]
    if not key.enabled:
        errors.append(f"disabled key_id: {receipt.key_id}")
    expected_authority = EXPECTED_AUTHORITIES[receipt.receipt_type]
    if receipt.authority is not expected_authority:
        errors.append(
            f"wrong receipt authority for {receipt.receipt_type}: "
            f"expected={expected_authority} actual={receipt.authority}"
        )
    if key.authority is not expected_authority:
        errors.append(
            f"wrong key authority for {receipt.key_id}: "
            f"expected={expected_authority} actual={key.authority}"
        )
    if receipt.release_id != release_id:
        errors.append(f"receipt release_id mismatch: {receipt.receipt_type}")
    if receipt.release_sha256 != release_sha256:
        errors.append(f"receipt release_sha256 mismatch: {receipt.receipt_type}")
    if not verify_mapping_ed25519(
        receipt.unsigned_payload(), receipt.signature, key.public_key
    ):
        errors.append(f"invalid signature: {receipt.receipt_type}")
    expected = EXPECTED_ARTIFACTS[receipt.receipt_type]
    if set(receipt.artifact_ids) != expected:
        errors.append(
            f"unexpected artifact set for {receipt.receipt_type}: "
            f"expected={sorted(expected)} actual={sorted(receipt.artifact_ids)}"
        )
    if receipt.receipt_type in {
        ReceiptType.P4_CONSUMPTION,
        ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION,
    }:
        if not receipt.downstream_output_id or not receipt.downstream_output_hash:
            errors.append("P4 consumption must prove a downstream output")
    elif receipt.downstream_output_id is not None or receipt.downstream_output_hash is not None:
        errors.append(
            f"downstream output is not allowed for {receipt.receipt_type}"
        )
    if receipt.receipt_type is ReceiptType.P9_FEEDBACK:
        if (
            not receipt.source_cycle_id
            or not receipt.target_cycle_id
            or receipt.source_cycle_id == receipt.target_cycle_id
        ):
            errors.append("P9 feedback must target a later cycle")
    if receipt.receipt_type is ReceiptType.N_PLUS_1_FEEDBACK:
        if (
            not receipt.source_cycle_id
            or not receipt.target_cycle_id
            or receipt.source_cycle_id == receipt.target_cycle_id
        ):
            errors.append("N+1 ingestion must prove a cycle transition")
    return errors


def verify_required_receipts(
    receipts: tuple[SignedReceipt, ...],
    keyring: Mapping[str, PublicKeyRecord],
    required: set[ReceiptType],
    *,
    release_id: str,
    release_sha256: str,
) -> list[str]:
    errors: list[str] = []
    counts = Counter(item.receipt_type for item in receipts)
    for item in required:
        if counts[item] != 1:
            errors.append(f"expected exactly one {item}, got {counts[item]}")
    unexpected = set(counts) - required
    if unexpected:
        errors.append(f"unexpected receipt types: {sorted(str(item) for item in unexpected)}")
    for receipt in receipts:
        errors.extend(
            verify_receipt(
                receipt,
                keyring,
                release_id=release_id,
                release_sha256=release_sha256,
            )
        )
    return errors
