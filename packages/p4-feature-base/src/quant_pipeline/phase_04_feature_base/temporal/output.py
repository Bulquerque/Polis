from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import ExecutionContext
from ..runtime.canonical import content_hash, deterministic_id
from ..runtime.datetime_utils import utc_z
from ..runtime.schema_validation import validate_json_schema
from .errors import TemporalContractError, TemporalErrorCode


def build_s2_artifact(
    *,
    name: str,
    module_id: str,
    context: ExecutionContext,
    records: list[dict[str, Any]],
    schema: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "name": name,
        "module_id": module_id,
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "decision_time": utc_z(context.decision_time),
        "records": records,
        "extra": dict(extra or {}),
    }
    artifact = {
        "artifact_id": deterministic_id(name.replace("_", "-"), identity),
        "artifact_name": name,
        "schema_id": f"p4.s2.{name}.v1",
        "schema_version": "1.0.0",
        "created_at": utc_z(context.created_at),
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "decision_time": utc_z(context.decision_time),
        "pipeline_version": context.pipeline_version,
        "lineage_id": deterministic_id(f"lineage-{name.replace('_', '-')}", identity, 24),
        "producer_module_id": module_id,
        "status": "READY",
        "records": records,
        **dict(extra or {}),
    }
    artifact["content_hash"] = content_hash(
        {key: value for key, value in artifact.items() if key != "content_hash"}
    )
    try:
        validate_json_schema(artifact, schema, name)
    except Exception as exc:
        raise TemporalContractError(
            TemporalErrorCode.OUTPUT_INVALID,
            str(exc),
            path=name,
        ) from exc
    return artifact
