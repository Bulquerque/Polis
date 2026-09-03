from __future__ import annotations

from ._p0_s6_core import digest, envelope, require_config, require_inputs, result, s6_control, validate
from ._p0_s6_render import file_entries, render_dashboard, write_files

REQUIRED = ["global_control_tower_payload", "phase_health_panel"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    inputs = require_inputs(inputs, set(REQUIRED))
    config = require_config(config)
    tower = s6_control(inputs[REQUIRED[0]], REQUIRED[0])
    panel = s6_control(inputs[REQUIRED[1]], REQUIRED[1])
    _validate_inputs(tower, panel)
    files = render_dashboard(tower, panel)
    entries = file_entries(files)
    materialized = False
    output_dir = config.get("dashboard_output_dir")
    if output_dir:
        entries = write_files(files, output_dir)
        materialized = True
    outputs = _build_outputs(tower, panel, files, entries, materialized, config)
    for name, artifact in outputs.items():
        validate(artifact, f"{name}.schema.yaml", name)
    return result("P0.S6.M04", "dashboard_exporter", REQUIRED, outputs)


def _validate_inputs(tower: dict, panel: dict) -> None:
    if tower.get("phase_count") != panel.get("phase_count"):
        raise ValueError("dashboard inputs disagree on phase_count")
    if not isinstance(panel.get("phase_statuses"), list) or len(panel["phase_statuses"]) != panel["phase_count"]:
        raise ValueError("phase_health_panel is incomplete")


def _build_outputs(tower: dict, panel: dict, files: dict[str, str], entries: list[dict], materialized: bool, config: dict) -> dict:
    payload_data = {"control_tower": tower, "phase_health_panel": panel}
    payload_hash = digest(payload_data)
    status = tower["status"]
    blocking = tower["release_blocking"]
    payloads = envelope("dashboard_json_payloads", payload_data, config)
    payloads.update(
        {
            "format": "json",
            "payload_sha256": payload_hash,
            "payloads": payload_data,
            "file_entries": entries,
            "status": status,
            "release_blocking": blocking,
            "promotion_blocked": True,
        }
    )
    site_hash = digest({entry["path"]: entry["sha256"] for entry in entries})
    site = envelope("dashboard_static_site", {"files": entries, "payload": payloads["lineage_id"]}, config)
    site.update(
        {
            "format": "html",
            "entrypoint": "index.html",
            "content_sha256": site_hash,
            "source_payload_lineage_id": payloads["lineage_id"],
            "file_entries": entries,
            "materialized": materialized,
            "status": status,
            "release_blocking": blocking,
            "promotion_blocked": True,
        }
    )
    manifest_entries = [
        {"path": entry["path"], "sha256": entry["sha256"], "size_bytes": entry["size_bytes"]}
        for entry in entries
    ]
    manifest = envelope("dashboard_export_manifest", manifest_entries, config)
    manifest.update(
        {
            "entry_count": len(manifest_entries),
            "entries": manifest_entries,
            "blocking_sources": list(tower.get("blocking_sources", [])),
            "status": status,
            "release_blocking": blocking,
            "promotion_blocked": True,
        }
    )
    return {
        "dashboard_export_manifest": manifest,
        "dashboard_static_site": site,
        "dashboard_json_payloads": payloads,
    }
