from datetime import UTC, datetime
import base64
import pytest

from quant_pipeline.phase_03_agents_rag_memory.final_integration.hashing import (
    public_key_base64,
    sign_mapping_ed25519,
)
from quant_pipeline.phase_03_agents_rag_memory.final_integration.models import Authority, PublicKeyRecord
from quant_pipeline.phase_03_agents_rag_memory.foundation.temporal_authority.errors import S2ContractError
from quant_pipeline.phase_03_agents_rag_memory.foundation.temporal_authority.overlay import normalize_temporal_artifact
from quant_pipeline.phase_03_agents_rag_memory.orchestration.registry import MODULE_REGISTRY
from quant_pipeline.phase_03_agents_rag_memory.orchestration.runtime_qualification_gate import (
    RuntimeServiceReceipt,
    validate_runtime_bundle,
)

PRIVATE_KEY = base64.b64encode(b"r" * 32).decode("ascii")
RELEASE_HASH = "a" * 64


def signed_service_receipt(service: str) -> dict[str, object]:
    raw = {
        "service": service,
        "status": "PASS",
        "provider_id": f"provider-{service.lower()}",
        "endpoint_hash": "b" * 64,
        "test_suite_hash": "c" * 64,
        "evidence_hash": "d" * 64,
        "release_id": "P3_TEST",
        "release_sha256": RELEASE_HASH,
        "authority": "OPERATIONS",
        "key_id": "operations-key",
        "signature": base64.b64encode(b"\0" * 64).decode("ascii"),
    }
    provisional = RuntimeServiceReceipt.model_validate(raw, strict=True)
    raw["signature"] = sign_mapping_ed25519(provisional.unsigned_payload(), PRIVATE_KEY)
    return RuntimeServiceReceipt.model_validate(raw, strict=True).model_dump(mode="json")


def runtime_bundle() -> dict[str, object]:
    return {
        "release_id": "P3_TEST",
        "release_sha256": RELEASE_HASH,
        "execution_mode": "PRODUCTION",
        "service_receipts": [
            signed_service_receipt(service)
            for service in ("MCP", "NEO4J", "OBJECT_STORAGE", "LLM")
        ],
        "execution_trace": [
            {
                "module_id": entry.module_id,
                "source_kind": "REAL_PIPELINE",
                "status": "PASS",
                "output_hash": "e" * 64,
            }
            for entry in MODULE_REGISTRY
        ],
        "p2_handoff_hash": "f" * 64,
        "checkpoint_reload_hash": "1" * 64,
        "next_cycle_hash": "2" * 64,
    }


def test_temporal_overlay() -> None:
    artifact = {"records": [{"created_at": "2025-01-01T01:00:00Z"}]}
    output = normalize_temporal_artifact(
        "clean_context_source_panel",
        artifact,
        as_of_time="2025-01-02T00:00:00Z",
    )
    assert output["records"][0]["available_at"]
    with pytest.raises(S2ContractError):
        normalize_temporal_artifact(
            "clean_event_reference_panel",
            {"records": [{}]},
            as_of_time="2025-01-02T00:00:00Z",
        )


def test_runtime_gate_fails_closed_and_passes_complete() -> None:
    keyring = {
        "operations-key": PublicKeyRecord(
            authority=Authority.OPERATIONS,
            public_key=public_key_base64(PRIVATE_KEY),
        )
    }
    bundle = runtime_bundle()
    assert validate_runtime_bundle(
        bundle,
        keyring=keyring,
        release_id="P3_TEST",
        release_sha256=RELEASE_HASH,
    ).status == "PASS"
    bundle["service_receipts"] = bundle["service_receipts"][:-1]
    assert validate_runtime_bundle(
        bundle,
        keyring=keyring,
        release_id="P3_TEST",
        release_sha256=RELEASE_HASH,
    ).status == "FAIL_NOT_QUALIFIED"
