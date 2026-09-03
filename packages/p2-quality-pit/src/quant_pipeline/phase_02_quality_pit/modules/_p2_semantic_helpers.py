from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from ._module_executor import ContractValidationError, _stable_digest


FORBIDDEN = {"target", "future_return", "label", "prediction", "candidate_id", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "realized_pnl"}


def require_inputs(inputs: dict, required: list[str]) -> None:
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    if FORBIDDEN.intersection(inputs):
        raise ContractValidationError(f"forbidden input fields detected: {sorted(FORBIDDEN.intersection(inputs))}")


def records(value, artifact: str) -> list[dict]:
    if isinstance(value, dict):
        for key in ("records", "rows", "items", "sources", "snapshots", "checks", "hints", "errors", "tasks"):
            if isinstance(value.get(key), list):
                return [dict(item) for item in value[key] if isinstance(item, dict)]
        if value.get("source"):
            raise ContractValidationError(f"{artifact} cannot be synthesized from source")
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    raise ContractValidationError(f"{artifact} must contain records")


def meta(artifact: str, payload, config: dict) -> dict:
    digest = _stable_digest(payload)
    created_at = config.get("created_at") or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "artifact_id": f"{artifact}-{digest[:12]}",
        "created_at": created_at,
        "lineage_id": f"lineage-{artifact}-{digest[:12]}",
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
    }


def artifact(artifact_name: str, rows: list[dict], config: dict, **extra) -> dict:
    # P3.S2 indexes quality decisions by (artifact_name, record_id).  P2
    # outputs must therefore carry a stable per-record identity instead of
    # relying on a consumer-side positional fallback.
    materialized_rows = [
        ({"record_id": f"{artifact_name}:{index}"} | dict(row))
        if not row.get("record_id")
        else dict(row)
        for index, row in enumerate(rows)
    ]
    result = {**meta(artifact_name, materialized_rows, config), "schema_version": f"{artifact_name}.v1", **extra}
    if materialized_rows:
        result.update({key: value for key, value in materialized_rows[0].items() if key not in FORBIDDEN})
    result["records"] = materialized_rows
    return result


def source_rows(value, artifact: str) -> list[dict]:
    rows = records(value, artifact)
    if not rows:
        raise ContractValidationError(f"{artifact} must not be empty")
    for row in rows:
        if not row.get("source_id"):
            raise ContractValidationError("source_id is required")
    return rows


def available_at(row: dict) -> str:
    value = row.get("available_at") or row.get("declared_available_at")
    if not value:
        raise ContractValidationError("available_at is required")
    return str(value)


def reject_future(row: dict, as_of: str | None) -> None:
    if as_of and available_at(row) > str(as_of):
        raise ContractValidationError("no_future_availability violation")


def no_forbidden_rows(rows: list[dict]) -> None:
    leaked = sorted({key for row in rows for key in row if key in FORBIDDEN})
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def stable_key(row: dict, fields: tuple[str, ...]) -> str:
    values = tuple(row.get(field) for field in fields)
    if any(value in (None, "") for value in values):
        raise ContractValidationError(f"missing deterministic key fields: {fields}")
    return json.dumps(values, sort_keys=True, default=str)
