from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_09.api.adapters.p8_rc4_1_legacy import (
    LEGACY_ROLES,
    LegacyArtifactSpec,
    LegacyP8RC41Adapter,
)
from quant_pipeline.phase_09.contracts.base import Availability
from quant_pipeline.phase_09.contracts.handoff import P8HandoffMode
from quant_pipeline.phase_09.contracts.integrity import sha256_bytes
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import (
    ArtifactStoreError,
    FileArtifactStore,
    InMemoryArtifactStore,
)


def test_file_store_rejects_path_escape(tmp_path) -> None:
    store = FileArtifactStore(tmp_path)
    with pytest.raises(ArtifactStoreError):
        store.write_bytes("../escape.bin", b"x")
    with pytest.raises(ArtifactStoreError):
        store.read_bytes("/absolute/path")


def test_file_store_atomic_round_trip(tmp_path) -> None:
    store = FileArtifactStore(tmp_path)
    location = store.write_bytes("nested/value.bin", b"payload")
    assert store.read_bytes(location) == b"payload"
    assert not list(tmp_path.rglob("*.tmp"))


def test_legacy_adapter_is_explicitly_limited_and_never_invents_missing_roles() -> None:
    store = InMemoryArtifactStore()
    ranking = json.dumps({"records": [{"candidate_id": "c1"}]}).encode()
    payloads = {"ranking_context_snapshot": ranking}
    specs = {
        "ranking_context_snapshot": LegacyArtifactSpec(
            schema_name="ranking_context_snapshot",
            schema_version="1.0.0",
            schema_sha256=sha256_bytes(b"schema"),
            producer_module_id="P8.S5.M03",
            artifact_type="ranking_context_snapshot",
        )
    }

    handoff = LegacyP8RC41Adapter(store).adapt(
        artifact_payloads=payloads,
        artifact_specs=specs,
        run_id="run-legacy",
        cycle_id="cycle-legacy",
        backtest_id="backtest-legacy",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert handoff.payload.mode is P8HandoffMode.LEGACY_RC4_1_LIMITED
    assert len(handoff.payload.artifacts) == len(LEGACY_ROLES)
    present = handoff.payload.slot("ranking_context_snapshot")
    assert present is not None and present.reference is not None
    assert present.reference.availability is Availability.LIMITED
    missing = handoff.payload.slot("ordered_event_ledger")
    assert missing is None  # role is not a legacy output and must not be invented
    assert any(slot.reference is None for slot in handoff.payload.artifacts)
