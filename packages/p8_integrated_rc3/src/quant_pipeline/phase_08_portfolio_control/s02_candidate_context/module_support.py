
"""Shared mechanics for S2; no economic decision logic lives here."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, finalize_content_hash
from quant_pipeline.phase_08_contracts.common import ModuleReceipt
from quant_pipeline.phase_08_contracts.enums import ReceiptStatus

from .contracts.bundle import S2InputBundleV1
from .errors import InputBundleIntegrityError


def build_receipt(*, module_id: str, inputs: tuple[object, ...], output: object, computed_at: object,
                  reason_codes: tuple[str, ...] = ()) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        input_hashes=tuple(canonical_sha256(value) for value in inputs),
        output_hash=canonical_sha256(output),
        computed_at=computed_at,
        reason_codes=reason_codes,
    )


def validate_s2_input_bundle(bundle: S2InputBundleV1) -> None:
    expected_bundle_hash = canonical_sha256(bundle, exclude_keys=frozenset({"content_sha256"}))
    if expected_bundle_hash != bundle.content_sha256:
        raise InputBundleIntegrityError("S2 input bundle embedded hash mismatch")
    snapshot = bundle.snapshot
    expected_snapshot_hash = canonical_sha256(snapshot, exclude_keys=frozenset({"content_sha256"}))
    if expected_snapshot_hash != snapshot.content_sha256:
        raise InputBundleIntegrityError("S1 snapshot embedded hash mismatch")
    checks = {
        "phase7_handoff_hash": canonical_sha256(bundle.validated_handoff),
        "candidate_ledger_hash": canonical_sha256(bundle.terminal_ledger),
        "resolved_evidence_hash": canonical_sha256(bundle.resolved_evidence),
        "feedback_context_hash": canonical_sha256(bundle.feedback_context),
        "portfolio_state_hash": canonical_sha256(bundle.current_state),
    }
    for field_name, actual in checks.items():
        expected = getattr(snapshot, field_name)
        if actual != expected:
            raise InputBundleIntegrityError(f"snapshot component hash mismatch: {field_name}")
    handoff = bundle.validated_handoff.handoff
    if handoff.run_id != snapshot.run_id or handoff.cycle_id != snapshot.cycle_id:
        raise InputBundleIntegrityError("P7 handoff run/cycle differs from snapshot")
    if tuple(sorted(handoff.received_candidate_ids)) != tuple(sorted(snapshot.received_candidate_ids)):
        raise InputBundleIntegrityError("snapshot candidate universe differs from P7 handoff")


def seal[T](model: T) -> T:
    return finalize_content_hash(model)
