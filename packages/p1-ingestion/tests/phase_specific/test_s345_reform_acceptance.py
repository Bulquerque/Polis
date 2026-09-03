from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest


CONFIG = {"created_at": "2026-07-23T00:00:00Z", "pipeline_version": "V14.1-RC4.1", "ingestion_run_id": "RUN-S345"}


def test_s3_writer_supports_multiple_captures_from_same_source(tmp_path: Path):
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M01_raw_artifact_writer")
    inventory = {
        "records": [
            {"source_id": "lse", "task_id": "t1", "raw_bytes": b"page-1", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l1"},
            {"source_id": "lse", "task_id": "t2", "raw_bytes": b"page-2", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l2"},
        ]
    }
    result = module.run_module(
        {"b3_raw_capture_inventory": {"records": []}, "non_b3_raw_capture_inventory": inventory},
        {**CONFIG, "artifact_root": str(tmp_path)},
    )["outputs"]["raw_file_inventory"]
    records = result["records"]
    assert len(records) == 2
    assert len({r["capture_id"] for r in records}) == 2
    assert len({r["artifact_id"] for r in records}) == 2
    assert all(Path(r["artifact_path"]).is_file() for r in records)


def test_s3_hash_is_exact_bytes_independent_of_input_route(tmp_path: Path):
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M02_hash_version_manager")
    file_path = tmp_path / "abc.bin"
    file_path.write_bytes(b"abc")
    inventory = {
        "records": [
            {"artifact_id": "a-inline", "source_id": "s", "raw_bytes": b"abc", "lineage_id": "l1"},
            {"artifact_id": "a-file", "source_id": "s", "artifact_path": str(file_path), "lineage_id": "l2"},
        ]
    }
    rows = module.run_module({"raw_file_inventory": inventory, "raw_artifact_store": inventory}, CONFIG)["outputs"]["versioned_raw_file_inventory"]["records"]
    expected = hashlib.sha256(b"abc").hexdigest()
    assert [row["file_hash"] for row in rows] == [expected, expected]
    assert all(row["hash_verified"] for row in rows)


def test_s4_invalid_json_is_reported_without_killing_schema_hint_pipeline():
    readability_module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M01_raw_readability_checker")
    hint_module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M02_raw_schema_hint_detector")
    versioned = {
        "records": [
            {
                "artifact_id": "a1",
                "raw_artifact_id": "a1",
                "capture_id": "c1",
                "task_id": "t1",
                "source_id": "s1",
                "raw_bytes": b"{bad json",
                "format": "json",
                "file_hash": "h",
                "file_size_bytes": 9,
                "lineage_id": "l1",
            }
        ]
    }
    readability = readability_module.run_module({"versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["raw_readability_report"]
    assert readability["checks"][0]["readability_status"] == "unreadable"
    assert readability["checks"][0]["issue"] == "invalid_json"
    hints = hint_module.run_module({"versioned_raw_file_inventory": versioned, "raw_readability_report": readability}, CONFIG)["outputs"]["raw_schema_hint_report"]
    assert hints["hints"][0]["hint_status"] == "not_applicable"
    assert hints["hints"][0]["is_clean_schema"] is False


def _s5_multi_capture_inputs():
    source_registry = {"sources": [{"source_id": "lse", "source_type": "api", "source_category": "market"}]}
    tasks = {
        "tasks": [
            {"task_id": "t1", "source_id": "lse", "lineage_id": "lt1", "available_at": "2026-01-01T00:00:00Z"},
            {"task_id": "t2", "source_id": "lse", "lineage_id": "lt2", "available_at": "2026-01-01T00:00:00Z"},
        ]
    }
    versioned = {
        "records": [
            {"task_id": "t1", "capture_id": "c1", "source_id": "lse", "artifact_id": "a1", "raw_artifact_id": "a1", "artifact_path": "raw/a1", "file_hash": "h1", "file_size_bytes": 3, "available_at": "2026-01-01T00:00:00Z", "lineage_id": "l1"},
            {"task_id": "t2", "capture_id": "c2", "source_id": "lse", "artifact_id": "a2", "raw_artifact_id": "a2", "artifact_path": "raw/a2", "file_hash": "h2", "file_size_bytes": 4, "available_at": "2026-01-01T00:00:00Z", "lineage_id": "l2"},
        ]
    }
    raw_file_inventory = {"records": [dict(row) for row in versioned["records"]]}
    readability = {
        "checks": [
            {"task_id": "t1", "capture_id": "c1", "artifact_id": "a1", "source_id": "lse", "readability_status": "readable", "issue_codes": []},
            {"task_id": "t2", "capture_id": "c2", "artifact_id": "a2", "source_id": "lse", "readability_status": "unreadable", "issue": "invalid_json", "issue_codes": ["invalid_json"]},
        ]
    }
    hints = {
        "hints": [
            {"task_id": "t1", "capture_id": "c1", "artifact_id": "a1", "source_id": "lse", "schema_fingerprint": "fp1", "is_clean_schema": False},
            {"task_id": "t2", "capture_id": "c2", "artifact_id": "a2", "source_id": "lse", "schema_fingerprint": None, "is_clean_schema": False, "hint_status": "not_applicable"},
        ]
    }
    return source_registry, tasks, raw_file_inventory, versioned, readability, hints


def test_s5_supports_multiple_snapshots_same_source_and_nonblocking_partial_handoff():
    source_registry, tasks, raw_file_inventory, versioned, readability, hints = _s5_multi_capture_inputs()
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder")
    m04 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M04_phase2_handoff_packager")

    manifest = m01.run_module({"source_registry": source_registry, "capture_task_manifest": tasks, "versioned_raw_file_inventory": versioned, "raw_readability_report": readability, "raw_schema_hint_report": hints}, CONFIG)["outputs"]["ingestion_manifest"]
    assert [r["final_state"] for r in manifest["task_results"]] == ["SUCCESS", "PARTIAL"]
    snapshots = m02.run_module({"source_registry": source_registry, "ingestion_manifest": manifest, "versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["source_snapshot_registry"]
    assert len(snapshots["snapshots"]) == 2
    assert len({s["snapshot_id"] for s in snapshots["snapshots"]}) == 2
    errors = m03.run_module({"ingestion_manifest": manifest, "raw_readability_report": readability, "capture_task_manifest": tasks}, CONFIG)["outputs"]["ingestion_error_report"]
    assert errors["error_count"] == 1
    assert errors["errors"][1]["error_code"] == "INVALID_CONTENT"
    assert errors["errors"][1]["is_blocking"] is False

    handoff = m04.run_module({
        "ingestion_manifest": manifest,
        "source_registry": source_registry,
        "source_snapshot_registry": snapshots,
        "raw_file_inventory": raw_file_inventory,
        "versioned_raw_file_inventory": versioned,
        "raw_readability_report": readability,
        "raw_schema_hint_report": hints,
        "ingestion_error_report": errors,
    }, CONFIG)["outputs"]["handoff_manifest_to_phase_2"]
    assert len(handoff["records"]) == 2
    assert len({r["handoff_artifact_id"] for r in handoff["records"]}) == 2
    assert handoff["records"][1]["warning_flag"] is True
    assert handoff["records"][0]["source_reference_date"] is None


def test_s5_ignores_unavailable_optional_secondary_without_partial_or_error():
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder")
    source_registry = {"sources": [{"source_id": "secondary-options", "authority_role": "secondary", "critical": False}]}
    tasks = {"tasks": [{
        "task_id": "secondary-task",
        "source_id": "secondary-options",
        "authority_role": "secondary",
        "lineage_id": "secondary-lineage",
        "critical": False,
    }]}
    manifest = m01.run_module({
        "source_registry": source_registry,
        "capture_task_manifest": tasks,
        "versioned_raw_file_inventory": {"records": [], "attempts": [{"task_id": "secondary-task", "state": "UNAVAILABLE", "error_code": "UPSTREAM_REJECTED"}]},
        "raw_readability_report": {"checks": []},
        "raw_schema_hint_report": {"hints": []},
    }, CONFIG)["outputs"]["ingestion_manifest"]
    assert manifest["task_results"][0]["final_state"] == "NOT_APPLICABLE"
    assert manifest["explicit_failures"] == []
    errors = m03.run_module({
        "ingestion_manifest": manifest,
        "raw_readability_report": {"checks": []},
        "capture_task_manifest": tasks,
    }, CONFIG)["outputs"]["ingestion_error_report"]
    assert errors["error_count"] == 0
    assert errors["errors"][0]["error_flag"] is False


def test_s5_blocking_failure_prevents_phase2_handoff():
    source_registry, tasks, raw_file_inventory, versioned, readability, hints = _s5_multi_capture_inputs()
    tasks["tasks"][1]["critical"] = True
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder")
    m04 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M04_phase2_handoff_packager")
    manifest = m01.run_module({"source_registry": source_registry, "capture_task_manifest": tasks, "versioned_raw_file_inventory": versioned, "raw_readability_report": readability, "raw_schema_hint_report": hints}, CONFIG)["outputs"]["ingestion_manifest"]
    snapshots = m02.run_module({"source_registry": source_registry, "ingestion_manifest": manifest, "versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["source_snapshot_registry"]
    errors = m03.run_module({"ingestion_manifest": manifest, "raw_readability_report": readability, "capture_task_manifest": tasks}, CONFIG)["outputs"]["ingestion_error_report"]
    assert errors["blocking_error_count"] == 1
    with pytest.raises(Exception, match="no_blocking_error_open"):
        m04.run_module({
            "ingestion_manifest": manifest,
            "source_registry": source_registry,
            "source_snapshot_registry": snapshots,
            "raw_file_inventory": raw_file_inventory,
            "versioned_raw_file_inventory": versioned,
            "raw_readability_report": readability,
            "raw_schema_hint_report": hints,
            "ingestion_error_report": errors,
        }, CONFIG)


def test_full_pipeline_propagates_real_run_id_and_keeps_reference_distinct(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "fred.json"
    raw.write_text('{"observations":[{"date":"2026-01-01","value":"1.0"}]}', encoding="utf-8")
    inputs = {
        "source_registry_config": {"registry_id": "r"},
        "ingestion_run_config": {"run_id": "RUN-REAL-COMPAT"},
        "source_credentials_handle": {"handle_id": "env"},
        "source_calendar_config": {"calendar_id": "global"},
        "local_raw_file_paths": {"fred": str(raw)},
        "api_source_definitions": {"sources": [{
            "source_id": "fred",
            "source_name": "FRED",
            "source_type": "file",
            "source_category": "macro",
            "format": "json",
            "available_at": "2026-01-03T00:00:00Z",
            "reference_time": "2026-01-01",
        }]},
        "manual_source_definitions": {"sources": []},
    }
    out = runner.run_phase(inputs, {**CONFIG, "artifact_root": str(tmp_path / "artifacts")})["phase_outputs"]
    snapshot = out["source_snapshot_registry"]["snapshots"][0]
    handoff = out["handoff_manifest_to_phase_2"]["records"][0]
    assert snapshot["ingestion_run_id"] == "RUN-REAL-COMPAT"
    assert handoff["ingestion_run_id"] == "RUN-REAL-COMPAT"
    assert handoff["source_name"] == "FRED"
    assert handoff["source_reference_date"] == "2026-01-01"
    assert handoff["declared_available_at"] == "2026-01-03T00:00:00Z"
    assert handoff["source_reference_date"] != handoff["declared_available_at"]


def test_s2_assembler_supports_multiple_captures_from_same_source():
    fetch = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M03_macro_raw_fetcher")
    assembler = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M07_non_b3_capture_inventory_assembler")
    tasks = {"tasks": [
        {"task_id": "t1", "source_id": "fred", "source_category": "macro", "lineage_id": "l1", "raw_bytes": b"a", "available_at": "2026-01-01T00:00:00Z"},
        {"task_id": "t2", "source_id": "fred", "source_category": "macro", "lineage_id": "l2", "raw_bytes": b"b", "available_at": "2026-01-01T00:00:00Z"},
    ]}
    macro = fetch.run_module({"capture_task_manifest": tasks}, CONFIG)["outputs"]["macro_raw_capture_inventory"]
    empty = {"records": []}
    merged = assembler.run_module({
        "macro_raw_capture_inventory": macro,
        "benchmark_raw_capture_inventory": empty,
        "crypto_raw_capture_inventory": empty,
        "document_raw_capture_inventory": empty,
    }, CONFIG)["outputs"]["non_b3_raw_capture_inventory"]
    assert len(merged["records"]) == 2
    assert len({row["capture_id"] for row in merged["records"]}) == 2


def test_source_registry_rejects_nested_secret_material():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    with pytest.raises(Exception, match="credential material"):
        module.run_module({
            "source_registry_config": {},
            "api_source_definitions": {"sources": [{
                "source_id": "fred",
                "source_type": "api",
                "credentials": {"api_key": "SHOULD_NOT_BE_HERE"},
            }]},
            "manual_source_definitions": {"sources": []},
        }, CONFIG)


def test_file_backed_s3_s4_path_avoids_path_read_bytes(monkeypatch, tmp_path: Path):
    source = tmp_path / "large.json"
    source.write_text('{"rows":[' + ','.join('{"x":1}' for _ in range(10000)) + ']}', encoding="utf-8")

    def forbidden_read_bytes(self):
        raise AssertionError("Path.read_bytes must not be used for file-backed S3/S4 processing")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    writer = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M01_raw_artifact_writer")
    hasher = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M02_hash_version_manager")
    readable = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M01_raw_readability_checker")
    hint = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M02_raw_schema_hint_detector")
    inv = {"records": [{
        "source_id": "file-source",
        "task_id": "t-file",
        "capture_id": "capture-file",
        "source_file_path": str(source),
        "format": "json",
        "raw_preserved": True,
        "cleaning_applied": False,
        "lineage_id": "l-file",
    }]}
    written = writer.run_module({"b3_raw_capture_inventory": inv, "non_b3_raw_capture_inventory": {"records": []}}, {**CONFIG, "artifact_root": str(tmp_path / "store")})["outputs"]
    versioned = hasher.run_module({"raw_file_inventory": written["raw_file_inventory"], "raw_artifact_store": written["raw_artifact_store"]}, CONFIG)["outputs"]["versioned_raw_file_inventory"]
    report = readable.run_module({"versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["raw_readability_report"]
    hints = hint.run_module({"versioned_raw_file_inventory": versioned, "raw_readability_report": report}, CONFIG)["outputs"]["raw_schema_hint_report"]
    assert report["checks"][0]["readability_status"] == "readable"
    assert hints["hints"][0]["schema_fingerprint"]
