from __future__ import annotations

import hashlib

import pytest

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.infrastructure.artifact_store import (
    LocalArtifactStore,
)


def test_content_addressed_store_is_idempotent_and_verifies_digest(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = b"immutable payload"
    digest = hashlib.sha256(payload).hexdigest()
    first = store.put(digest, payload)
    second = store.put(digest, payload)
    assert first == second
    assert store.get(digest) == payload
    with pytest.raises(ValueError, match="does not match"):
        store.put("0" * 64, payload)


def test_existing_corrupted_object_is_detected(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    payload = b"immutable payload"
    digest = hashlib.sha256(payload).hexdigest()
    path = store.put(digest, payload)
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="collision or corrupted"):
        store.put(digest, payload)
