from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import BoundaryContractError, BoundaryErrorCode
from ..models import ExecutionContext
from .canonical import content_hash, deterministic_id
from .datetime_utils import utc_z
from .schema_validation import validate_json_schema


def build_artifact(
    *,
    name: str,
    module_id: str,
    context: ExecutionContext,
    records: list[dict[str, Any]],
    schema: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "name": name, "module_id": module_id, "run_id": context.run_id,
        "cycle_id": context.cycle_id, "as_of_time": utc_z(context.as_of_time),
        "records": records, "extra": dict(extra or {}),
    }
    artifact = {
        "artifact_id": deterministic_id(name.replace("_", "-"), identity),
        "artifact_name": name,
        "schema_id": f"p4.s1.{name}.v1",
        "schema_version": "1.0.0",
        "created_at": utc_z(context.created_at),
        "run_id": context.run_id,
        "cycle_id": context.cycle_id,
        "as_of_time": utc_z(context.as_of_time),
        "pipeline_version": context.pipeline_version,
        "lineage_id": deterministic_id(f"lineage-{name.replace('_', '-')}", identity, 24),
        "producer_module_id": module_id,
        "status": "READY",
        "records": records,
        **dict(extra or {}),
    }
    artifact["content_hash"] = content_hash({k: v for k, v in artifact.items() if k != "content_hash"})
    try:
        validate_json_schema(artifact, schema, name)
    except BoundaryContractError:
        raise
    except Exception as exc:
        raise BoundaryContractError(
            BoundaryErrorCode.OUTPUT_INVALID, str(exc), path=name
        ) from exc
    return artifact
