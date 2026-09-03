from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from quant_pipeline.phase_07_strategy_tournament.finalization.artifacts import artifact_reference, build_artifact
from quant_pipeline.phase_07_strategy_tournament.finalization.boundary.base import ArtifactEnvelope, HandoffManifestRecord

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def s8_input() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures/input/s8_handoff_fixture.json").read_text(encoding="utf-8"))


@pytest.fixture
def s8_config() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures/input/s8_config_fixture.json").read_text(encoding="utf-8"))


def rebuild(envelope: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    return build_artifact(
        artifact_name=envelope["artifact_name"],
        schema_version=envelope["schema_version"],
        producer_module_id=envelope["producer_module_id"],
        run_id=envelope["run_id"],
        cycle_id=envelope["cycle_id"],
        decision_time=datetime.fromisoformat(envelope["decision_time"].replace("Z", "+00:00")),
        available_at=datetime.fromisoformat(envelope["available_at"].replace("Z", "+00:00")),
        created_at=datetime.fromisoformat(envelope["created_at"].replace("Z", "+00:00")),
        lineage_id=envelope["lineage_id"],
        records=records,
    ).model_dump(mode="json")


def refresh_s7_manifest(
    payload: dict[str, Any],
    *,
    candidate_count: int | None = None,
    conservation_hash: str | None = None,
) -> dict[str, Any]:
    envelope = ArtifactEnvelope.model_validate(payload["rankability_handoff_manifest"])
    record = HandoffManifestRecord.model_validate(envelope.records[0])
    references = tuple(
        sorted(
            (artifact_reference(ArtifactEnvelope.model_validate(payload[ref.artifact_name])) for ref in record.artifact_references),
            key=lambda item: item.artifact_name,
        )
    )
    updates: dict[str, Any] = {"artifact_references": references}
    if candidate_count is not None:
        updates["candidate_count"] = candidate_count
    if conservation_hash is not None:
        updates["candidate_conservation_sha256"] = conservation_hash
    updated = record.model_copy(update=updates)
    payload["rankability_handoff_manifest"] = rebuild(
        payload["rankability_handoff_manifest"],
        [updated.model_dump(mode="json")],
    )
    return payload


def mutate_record(payload: dict[str, Any], artifact: str, candidate_id: str, **updates: Any) -> dict[str, Any]:
    result = deepcopy(payload)
    records = []
    found = False
    for row in result[artifact]["records"]:
        if row.get("candidate_id") == candidate_id:
            records.append({**row, **updates})
            found = True
        else:
            records.append(row)
    if not found:
        raise AssertionError(f"candidate not found: {candidate_id}")
    result[artifact] = rebuild(result[artifact], records)
    return refresh_s7_manifest(result)


def permute_referenced_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    manifest = HandoffManifestRecord.model_validate(result["rankability_handoff_manifest"]["records"][0])
    for ref in manifest.artifact_references:
        envelope = result[ref.artifact_name]
        result[ref.artifact_name] = rebuild(envelope, list(reversed(envelope["records"])))
    return refresh_s7_manifest(result)
