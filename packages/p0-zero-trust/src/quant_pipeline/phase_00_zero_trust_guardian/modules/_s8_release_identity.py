from __future__ import annotations

from typing import Any

from ._p0_s8_utils import digest


def collect_snapshot_digests(artifacts: list[dict[str, Any]], config: dict[str, Any]) -> list[str]:
    configured = config.get("source_snapshot_digest")
    values: set[str] = {str(configured)} if configured else set()
    for artifact in artifacts:
        values.update(_snapshot_values(artifact))
    return sorted(value for value in values if value)


def resolve_snapshot_identity(
    artifacts: list[dict[str, Any]],
    source_hashes: list[str],
    config: dict[str, Any],
) -> tuple[str, str, bool]:
    snapshots = collect_snapshot_digests(artifacts, config)
    if len(snapshots) > 1:
        return "MISMATCH", "", False
    if len(snapshots) == 1:
        return "BOUND", snapshots[0], True
    synthetic = digest({"material_source_hashes": sorted(source_hashes)})
    return "MATERIAL_ONLY", f"sha256:{synthetic}", True


def qualification_bindings(artifacts: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    configured = config.get("qualification_bindings")
    if isinstance(configured, list):
        return _normalize_bindings(configured)
    collected: list[dict[str, Any]] = []
    for artifact in artifacts:
        for key in ("qualification_bindings", "canonical_qualification_runs"):
            value = artifact.get(key)
            if isinstance(value, list):
                collected.extend(item for item in value if isinstance(item, dict))
    return _normalize_bindings(collected)


def evidence_set_id(artifacts: list[dict[str, Any]], config: dict[str, Any]) -> str:
    configured = config.get("evidence_set_id")
    if configured:
        return str(configured)
    for artifact in artifacts:
        value = artifact.get("evidence_set_id")
        if isinstance(value, str) and value:
            return value
    return ""


def release_fingerprint(material: dict[str, Any]) -> str:
    return f"sha256:{digest(material)}"


def _snapshot_values(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"source_snapshot_digest", "snapshot_digest"} and isinstance(child, str):
                found.add(child)
            elif key in {"metadata", "source_snapshot"} and isinstance(child, dict):
                found.update(_snapshot_values(child))
    return found


def _normalize_bindings(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in value:
        phase_id = item.get("phase_id")
        run_id = item.get("run_id", item.get("qualification_run_id"))
        status = item.get("status", item.get("qualification_status"))
        if isinstance(phase_id, str) and isinstance(run_id, str):
            normalized.append({"phase_id": phase_id, "run_id": run_id, "status": str(status or "UNKNOWN")})
    normalized.sort(key=lambda item: (item["phase_id"], item["run_id"]))
    return normalized
