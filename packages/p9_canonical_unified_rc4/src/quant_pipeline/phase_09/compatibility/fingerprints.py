from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from .errors import ContractMismatchError, PhaseUnavailableError
from .models import CompatibilityReceipt, CompatibilityState
from .registry import load_cross_phase_compatibility_matrix


def verify_phase_package_fingerprint(
    *,
    phase_id: str,
    package_root: str | Path,
    checked_at: datetime,
) -> CompatibilityReceipt:
    """Verify the exact package snapshot qualified by the P9 compatibility matrix."""

    matrix = load_cross_phase_compatibility_matrix()
    entry = next((row for row in matrix["entries"] if row["phase_id"] == phase_id), None)
    if entry is None:
        raise ValueError(f"unsupported phase id: {phase_id}")
    root = Path(package_root).resolve()
    subject = root / str(entry["fingerprint_subject"])
    if not subject.is_file():
        raise PhaseUnavailableError(
            f"qualified fingerprint subject is absent for {phase_id}: {subject}"
        )
    actual = sha256(subject.read_bytes()).hexdigest()
    expected = str(entry["fingerprint_sha256"])
    if actual != expected:
        raise ContractMismatchError(
            f"{phase_id} package fingerprint mismatch: expected={expected} actual={actual}"
        )
    raw_state = str(entry["state"])
    state = CompatibilityState(raw_state)
    limitations: tuple[str, ...] = ()
    if state is CompatibilityState.COMPATIBLE_PROCESS_ISOLATED:
        limitations = (
            "the qualified P3 runtime is consumed through an isolated process boundary",
        )
    elif state is CompatibilityState.COMPATIBLE_GOVERNED:
        limitations = (
            "the qualified P6 package has no direct feedback consumer; activation remains P0-mediated",
        )
    elif state is CompatibilityState.COMPATIBLE_LIMITED:
        limitations = (
            "the qualified P8 native handoff requires explicit supplemental evidence for FULL mode",
        )
    return CompatibilityReceipt(
        phase_id=phase_id,
        package_name=str(entry["package_name"]),
        package_version=str(entry["package_version"]),
        contract_name=str(entry["boundary"]),
        contract_version="1.0.0",
        state=state,
        checked_at=checked_at.astimezone(UTC),
        source_payload_sha256=actual,
        limitations=limitations,
    )
