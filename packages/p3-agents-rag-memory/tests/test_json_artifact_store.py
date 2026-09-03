from __future__ import annotations

from pathlib import Path

import pytest

from quant_pipeline.phase_03_agents_rag_memory.integration import (
    ArtifactStorageError,
    JsonFileArtifactStore,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import (
    FoundationGovernanceView,
    StorageReference,
    StorageScheme,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "integration_contract_pack"


def test_json_store_publishes_and_resolves_atomically(tmp_path: Path) -> None:
    view = FoundationGovernanceView.model_validate_json(
        (FIXTURES / "foundation_governance_view.json").read_text(encoding="utf-8"),
        strict=True,
    )
    store = JsonFileArtifactStore(tmp_path)
    pointer = store.publish(view, producer_module_id="P3.S2.M02")

    assert pointer.storage_ref.scheme is StorageScheme.FILE
    assert not Path(pointer.storage_ref.location).is_absolute()
    assert store.resolve(pointer, FoundationGovernanceView) == view


def test_json_store_blocks_path_escape(tmp_path: Path) -> None:
    view = FoundationGovernanceView.model_validate_json(
        (FIXTURES / "foundation_governance_view.json").read_text(encoding="utf-8"),
        strict=True,
    )
    store = JsonFileArtifactStore(tmp_path)
    pointer = store.publish(view)
    escaped = pointer.model_copy(
        update={
            "storage_ref": StorageReference(
                scheme=StorageScheme.FILE,
                location="../escape.json",
            )
        }
    )
    with pytest.raises(ArtifactStorageError, match="escapes"):
        store.resolve(escaped, FoundationGovernanceView)


def test_json_store_rejects_payload_tampering_even_when_declared_hash_is_unchanged(tmp_path: Path) -> None:
    import json

    view = FoundationGovernanceView.model_validate_json(
        (FIXTURES / "foundation_governance_view.json").read_text(encoding="utf-8"),
        strict=True,
    )
    store = JsonFileArtifactStore(tmp_path)
    pointer = store.publish(view)
    path = tmp_path / pointer.storage_ref.location
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["selected_model_ref"] = "tampered-model"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactStorageError, match="hash mismatch"):
        store.resolve(pointer, FoundationGovernanceView)
