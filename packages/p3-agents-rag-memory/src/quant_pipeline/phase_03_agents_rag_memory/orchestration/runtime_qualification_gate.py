"""Fail-closed qualification of a production P3 runtime execution."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..final_integration.hashing import valid_sha256, verify_mapping_ed25519
from ..final_integration.models import Authority, PublicKeyRecord
from .registry import MODULE_REGISTRY

REQUIRED_SERVICES = {"MCP", "NEO4J", "OBJECT_STORAGE", "LLM"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeServiceReceipt(StrictModel):
    receipt_version: str = "p3.runtime-service-receipt.v2"
    service: Literal["MCP", "NEO4J", "OBJECT_STORAGE", "LLM"]
    status: Literal["PASS"]
    provider_id: str = Field(min_length=1)
    endpoint_hash: str
    test_suite_hash: str
    evidence_hash: str
    release_id: str
    release_sha256: str
    authority: Literal[Authority.OPERATIONS]
    key_id: str
    signature: str = Field(min_length=88, max_length=88)

    @field_validator(
        "endpoint_hash", "test_suite_hash", "evidence_hash", "release_sha256"
    )
    @classmethod
    def digest_is_valid(cls, value: str) -> str:
        if not valid_sha256(value):
            raise ValueError("expected lowercase SHA-256")
        return value

    def unsigned_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("signature", None)
        return payload


class RuntimeQualificationResult(StrictModel):
    status: Literal["PASS", "FAIL_NOT_QUALIFIED"]
    errors: tuple[str, ...]
    module_count: int
    service_types: tuple[str, ...]
    production_promotion_allowed: Literal[False] = False


def validate_runtime_bundle(
    bundle: Mapping[str, Any],
    *,
    keyring: Mapping[str, PublicKeyRecord],
    release_id: str,
    release_sha256: str,
) -> RuntimeQualificationResult:
    errors: list[str] = []
    if bundle.get("release_id") != release_id:
        errors.append("runtime bundle release_id mismatch")
    if bundle.get("release_sha256") != release_sha256:
        errors.append("runtime bundle release_sha256 mismatch")
    if bundle.get("execution_mode") != "PRODUCTION":
        errors.append("execution_mode must be PRODUCTION")

    receipts: list[RuntimeServiceReceipt] = []
    for raw in bundle.get("service_receipts", []):
        try:
            receipt = RuntimeServiceReceipt.model_validate(raw, strict=True)
        except Exception as exc:
            errors.append(f"invalid service receipt: {exc}")
            continue
        key = keyring.get(receipt.key_id)
        if key is None:
            errors.append(f"unknown service key: {receipt.key_id}")
        else:
            if not key.enabled:
                errors.append(f"disabled service key: {receipt.key_id}")
            if key.authority is not Authority.OPERATIONS:
                errors.append(f"service key is not owned by OPERATIONS: {receipt.key_id}")
            if not verify_mapping_ed25519(
                receipt.unsigned_payload(), receipt.signature, key.public_key
            ):
                errors.append(f"invalid service receipt signature: {receipt.service}")
        if receipt.release_id != release_id or receipt.release_sha256 != release_sha256:
            errors.append(f"service receipt release mismatch: {receipt.service}")
        receipts.append(receipt)

    counts = Counter(receipt.service for receipt in receipts)
    for service in REQUIRED_SERVICES:
        if counts[service] != 1:
            errors.append(f"expected exactly one service receipt for {service}")
    unexpected = set(counts) - REQUIRED_SERVICES
    if unexpected:
        errors.append(f"unexpected service receipts: {sorted(unexpected)}")

    trace = bundle.get("execution_trace", [])
    expected_modules = {entry.module_id for entry in MODULE_REGISTRY}
    module_ids: list[str] = []
    if not isinstance(trace, list):
        errors.append("execution_trace must be a list")
        trace = []
    for item in trace:
        if not isinstance(item, Mapping):
            errors.append("execution trace rows must be mappings")
            continue
        module_id = str(item.get("module_id", ""))
        module_ids.append(module_id)
        if item.get("source_kind") != "REAL_PIPELINE":
            errors.append(f"non-production trace source for {module_id}")
        if item.get("status") != "PASS":
            errors.append(f"module execution did not pass: {module_id}")
        artifact_hash = item.get("output_hash")
        if not isinstance(artifact_hash, str) or not valid_sha256(artifact_hash):
            errors.append(f"invalid output hash in trace: {module_id}")
    expected_module_count = len(expected_modules)
    if set(module_ids) != expected_modules or len(module_ids) != expected_module_count:
        errors.append(
            "execution trace must contain exactly "
            f"{expected_module_count} unique canonical production modules"
        )

    for name in ("p2_handoff_hash", "checkpoint_reload_hash", "next_cycle_hash"):
        value = bundle.get(name)
        if not isinstance(value, str) or not valid_sha256(value):
            errors.append(f"missing or invalid {name}")

    return RuntimeQualificationResult(
        status="PASS" if not errors else "FAIL_NOT_QUALIFIED",
        errors=tuple(errors),
        module_count=len(set(module_ids)),
        service_types=tuple(sorted(counts)),
    )


__all__ = [
    "RuntimeQualificationResult",
    "RuntimeServiceReceipt",
    "validate_runtime_bundle",
]
