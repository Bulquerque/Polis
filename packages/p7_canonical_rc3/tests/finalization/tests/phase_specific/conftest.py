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
def input_payload() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures/input/learning_handoff_fixture.json").read_text(encoding="utf-8"))


@pytest.fixture
def s7_config() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures/input/s7_config_fixture.json").read_text(encoding="utf-8"))


def rebuild_envelope(envelope: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    artifact = build_artifact(
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
    )
    return artifact.model_dump(mode="json")


def refresh_scoring_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    manifest_env = ArtifactEnvelope.model_validate(payload["hybrid_scoring_handoff_manifest"])
    record = HandoffManifestRecord.model_validate(manifest_env.records[0])
    references = tuple(
        artifact_reference(ArtifactEnvelope.model_validate(payload[ref.artifact_name]))
        for ref in record.artifact_references
    )
    updated_record = record.model_copy(update={"artifact_references": references})
    payload["hybrid_scoring_handoff_manifest"] = rebuild_envelope(
        payload["hybrid_scoring_handoff_manifest"],
        [updated_record.model_dump(mode="json")],
    )
    return payload


def mutate_record(
    payload: dict[str, Any], artifact_name: str, candidate_id: str, **updates: Any
) -> dict[str, Any]:
    result = deepcopy(payload)
    records = result[artifact_name]["records"]
    updated_records = []
    found = False
    for record in records:
        if record.get("candidate_id") == candidate_id:
            updated_records.append({**record, **updates})
            found = True
        else:
            updated_records.append(record)
    if not found:
        raise AssertionError(f"candidate {candidate_id} not found in {artifact_name}")
    result[artifact_name] = rebuild_envelope(result[artifact_name], updated_records)
    return refresh_scoring_manifest(result)


def remove_record(payload: dict[str, Any], artifact_name: str, candidate_id: str) -> dict[str, Any]:
    result = deepcopy(payload)
    records = [r for r in result[artifact_name]["records"] if r.get("candidate_id") != candidate_id]
    result[artifact_name] = rebuild_envelope(result[artifact_name], records)
    return refresh_scoring_manifest(result)


def permute_records(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    for name, envelope in list(result.items()):
        if name == "hybrid_scoring_handoff_manifest" or not isinstance(envelope, dict):
            continue
        if "records" in envelope:
            result[name] = rebuild_envelope(envelope, list(reversed(envelope["records"])))
    return refresh_scoring_manifest(result)
