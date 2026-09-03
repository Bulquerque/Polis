"""Shared mechanics for S1 modules; no economic decision logic lives here."""

from __future__ import annotations

import json
from decimal import Decimal

from pydantic import BaseModel, ValidationError

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference, ModuleReceipt
from quant_pipeline.phase_08_contracts.enums import ReceiptStatus

from .errors import ContractIntegrityError, HashMismatchError, TemporalIntegrityError


def load_json_object(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_int=int)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractIntegrityError("payload is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ContractIntegrityError("payload root must be a JSON object")
    return value


def validate_model_json[T: BaseModel](model_type: type[T], raw: bytes, *, label: str) -> T:
    try:
        return model_type.model_validate_json(raw, strict=True)
    except ValidationError as exc:
        raise ContractIntegrityError(f"{label} schema validation failed: {exc}") from exc


def verify_embedded_canonical_hash(payload: dict[str, object], *, field_name: str = "content_sha256") -> str:
    expected = payload.get(field_name)
    if not isinstance(expected, str):
        raise ContractIntegrityError(f"{field_name} must be present and textual")
    actual = canonical_sha256(payload, exclude_keys=frozenset({field_name}))
    if actual != expected:
        raise HashMismatchError(f"embedded canonical hash mismatch: expected={expected} actual={actual}")
    return actual




def verify_model_embedded_hash(model: BaseModel, *, field_name: str = "content_sha256") -> str:
    expected = getattr(model, field_name, None)
    if not isinstance(expected, str):
        raise ContractIntegrityError(f"{field_name} must be present and textual")
    actual = canonical_sha256(model, exclude_keys=frozenset({field_name}))
    if actual != expected:
        raise HashMismatchError(f"embedded canonical hash mismatch: expected={expected} actual={actual}")
    return actual

def read_verified_artifact(store: object, reference: ArtifactReference, *, decision_time: object) -> bytes:
    if reference.available_at > decision_time:
        raise TemporalIntegrityError(f"artifact becomes available after decision: {reference.artifact_id}")
    read = getattr(store, "read", None)
    if read is None:
        raise TypeError("artifact store does not implement read")
    raw = read(reference)
    actual = raw_sha256(raw)
    if actual != reference.content_sha256:
        raise HashMismatchError(
            f"artifact hash mismatch for {reference.artifact_id}: expected={reference.content_sha256} actual={actual}"
        )
    return raw


def build_receipt(
    *,
    module_id: str,
    status: ReceiptStatus,
    inputs: tuple[object, ...],
    output: object,
    computed_at: object,
    reason_codes: tuple[str, ...] = (),
) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id,
        status=status,
        input_hashes=tuple(canonical_sha256(value) for value in inputs),
        output_hash=canonical_sha256(output),
        computed_at=computed_at,
        reason_codes=reason_codes,
    )
