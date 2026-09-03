import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


CONFIG = {"pipeline_version": "V14.1-RC4.1", "created_at": "2024-01-01T00:00:00Z"}


def test_source_registry_loader_merges_explicit_api_and_manual_sources():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    result = module.run_module({
        "source_registry_config": {"registry_id": "test"},
        "api_source_definitions": {"sources": [{"source_id": "api-1", "source_type": "api"}]},
        "manual_source_definitions": {"sources": [{"source_id": "manual-1", "source_type": "manual"}]},
    }, CONFIG)
    sources = result["outputs"]["source_registry"]["sources"]
    assert {item["source_id"] for item in sources} == {"api-1", "manual-1"}, "source_id_unique"
    assert {item["source_type"] for item in sources} <= {"api", "manual"}, "source_type_allowed"
    assert len(sources) == 2, "manual_and_api_sources_explicit"


def test_source_registry_loader_rejects_duplicate_and_forbidden_input():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    base = {
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{"source_id": "same", "source_type": "api"}]},
        "manual_source_definitions": {"sources": [{"source_id": "same", "source_type": "manual"}]},
    }
    with pytest.raises(Exception, match="unique"):
        module.run_module(base, CONFIG)
    with pytest.raises(Exception, match="forbidden"):
        module.run_module({**base, "target": "leak"}, CONFIG)


def test_ingestion_run_validator_requires_run_calendar_and_non_materialized_credentials():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    inputs = {
        "ingestion_run_config": {"run_id": "run-1"},
        "source_credentials_handle": {"handle_id": "secret-ref"},
        "source_calendar_config": {"calendar_id": "NYSE"},
        "source_registry": {"sources": []},
    }
    result = module.run_module(inputs, CONFIG)
    validated = result["outputs"]["validated_ingestion_run_config"]
    assert validated["run_id"] == "run-1", "run_id_present"
    assert validated["credentials_materialized"] is False, "credentials_not_materialized"
    assert validated["calendar_declared"] is True, "calendar_declared"
    with pytest.raises(Exception, match="run_id"):
        module.run_module({**inputs, "ingestion_run_config": {}}, CONFIG)
    with pytest.raises(Exception, match="material"):
        module.run_module({**inputs, "source_credentials_handle": {"api_key": "not-allowed"}}, CONFIG)


def test_capture_orchestrator_requires_source_and_lineage_per_task():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M01_source_capture_orchestrator")
    result = module.run_module({"source_capture_plan": {"tasks": [{"task_id": "t1", "source_id": "s1", "lineage_id": "l1"}]}}, CONFIG)
    assert result["outputs"]["capture_task_manifest"]["tasks"][0]["source_id"] == "s1", "capture_task_has_source_id"
    assert result["outputs"]["capture_task_manifest"]["tasks"][0]["lineage_id"], "task_lineage_declared"
    with pytest.raises(Exception, match="source_id"):
        module.run_module({"source_capture_plan": {"tasks": [{"task_id": "t1"}]}}, CONFIG)


def test_source_availability_planner_marks_critical_sources_and_lineage():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    result = module.run_module({
        "validated_ingestion_run_config": {"run_id": "r1"},
        "source_registry": {"sources": [{"source_id": "s1", "source_type": "api", "critical": True}]},
        "source_calendar_config": {"calendar_id": "NYSE"},
        "local_raw_file_paths": ["raw/s1.bin"],
    }, CONFIG)
    task = result["outputs"]["source_capture_plan"]["tasks"][0]
    assert task["critical"] is True, "critical_sources_marked"
    assert task["lineage_id"], "source_plan_complete"


@pytest.mark.parametrize(("module_name", "artifact"), [
    ("P1_S2_M02_b3_cotahist_raw_fetcher", "b3_raw_capture_inventory"),
    ("P1_S2_M03_macro_raw_fetcher", "macro_raw_capture_inventory"),
    ("P1_S2_M04_benchmark_raw_fetcher", "benchmark_raw_capture_inventory"),
    ("P1_S2_M05_crypto_raw_fetcher", "crypto_raw_capture_inventory"),
    ("P1_S2_M06_document_raw_collector", "document_raw_capture_inventory"),
])
def test_raw_collectors_preserve_content_and_availability(module_name, artifact):
    module = importlib.import_module(f"quant_pipeline.phase_01_ingestion.modules.{module_name}")
    result = module.run_module({"capture_task_manifest": {"tasks": [{
        "task_id": "t1", "source_id": "s1", "lineage_id": "l1",
        "raw_bytes": b"raw-bytes", "available_at": "2024-01-01T00:00:00Z",
    }]}}, CONFIG)
    record = result["outputs"][artifact]
    assert record["raw_preserved"] is True, "raw_bytes_preserved"
    assert record["cleaning_applied"] is False, "no_economic_cleaning"
    assert record["records"][0]["source_id"] == "s1", "source_id_present"
    assert record["records"][0]["available_at"], "source_available_at_declared"
    assert record["records"][0].get("raw_bytes") or record["records"][0].get("raw_text") or record["records"][0].get("raw_preserved"), "raw_text_or_file_preserved"
    with pytest.raises(Exception, match="raw content"):
        module.run_module({"capture_task_manifest": {"tasks": [{"source_id": "s1", "lineage_id": "l1"}]}}, CONFIG)


def test_non_b3_assembler_accounts_for_each_source_without_cleaning():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M07_non_b3_capture_inventory_assembler")
    def inventory(source):
        return {"records": [{"source_id": source, "raw_preserved": True, "cleaning_applied": False, "lineage_id": f"l-{source}"}]}
    result = module.run_module({key: inventory(key) for key in ("macro_raw_capture_inventory", "benchmark_raw_capture_inventory", "crypto_raw_capture_inventory", "document_raw_capture_inventory")}, CONFIG)
    assert len(result["outputs"]["non_b3_raw_capture_inventory"]["records"]) == 4, "all_non_b3_sources_accounted"
    assert result["outputs"]["non_b3_raw_capture_inventory"]["cleaning_applied"] is False, "no_cleaning"


def test_raw_artifact_writer_creates_paths_and_preserves_raw(tmp_path):
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M01_raw_artifact_writer")
    inventory = {"records": [{"source_id": "s1", "raw_bytes": b"bytes", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l1"}]}
    result = module.run_module({"b3_raw_capture_inventory": inventory, "non_b3_raw_capture_inventory": {"records": []}}, {**CONFIG, "artifact_root": str(tmp_path)})
    record = result["outputs"]["raw_file_inventory"]["records"][0]
    assert record["path_exists"] is True, "artifact_path_exists"
    assert record["no_overwrite"] is True, "no_overwrite"
    assert (tmp_path / Path(record["artifact_path"]).name).read_bytes() == b"bytes"
    conflicting = {"records": [{"source_id": "s1", "raw_bytes": b"different", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l1"}]}
    with pytest.raises(Exception, match="no_overwrite"):
        module.run_module({"b3_raw_capture_inventory": conflicting, "non_b3_raw_capture_inventory": {"records": []}}, {**CONFIG, "artifact_root": str(tmp_path)})


def test_hash_version_and_readability_checks_are_explicit():
    hash_module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M02_hash_version_manager")
    readability = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M01_raw_readability_checker")
    hint = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M02_raw_schema_hint_detector")
    inventory = {"records": [{"artifact_id": "a1", "source_id": "s1", "raw_bytes": b"abc", "lineage_id": "l1"}]}
    versioned = hash_module.run_module({"raw_file_inventory": inventory, "raw_artifact_store": inventory}, CONFIG)["outputs"]["versioned_raw_file_inventory"]
    assert versioned["records"][0]["file_hash"], "hash_present"
    assert versioned["records"][0]["file_size_bytes"] == 3, "file_size_positive"
    assert len({row["artifact_id"] for row in versioned["records"]}) == len(versioned["records"]), "artifact_id_unique"
    readable = readability.run_module({"versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["raw_readability_report"]
    assert readable["checks"][0]["readability_status"] == "readable", "readability_status_present"
    assert readable["checks"][0].get("empty_file_flagged") is False, "empty_file_flagged"
    hints = hint.run_module({"versioned_raw_file_inventory": versioned, "raw_readability_report": readable}, CONFIG)["outputs"]["raw_schema_hint_report"]
    assert hints["hints"][0]["is_clean_schema"] is False, "schema_hint_not_clean_schema"


def _s5_inputs():
    source_registry = {"sources": [{"source_id": "s1", "source_type": "api"}]}
    tasks = {"tasks": [{"task_id": "t1", "source_id": "s1", "lineage_id": "l1", "available_at": "2024-01-01T00:00:00Z"}]}
    versioned = {"records": [{"source_id": "s1", "artifact_id": "a1", "artifact_path": "raw/s1.bin", "file_hash": "h1", "file_size_bytes": 3, "available_at": "2024-01-01T00:00:00Z", "lineage_id": "l1"}]}
    readable = {"checks": [{"source_id": "s1", "readability_status": "readable"}]}
    hints = {"hints": [{"source_id": "s1", "is_clean_schema": False}]}
    return source_registry, tasks, versioned, readable, hints


def test_s5_builds_manifest_snapshot_error_report_and_handoff_with_explicit_gates():
    source_registry, tasks, versioned, readable, hints = _s5_inputs()
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder")
    m04 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M04_phase2_handoff_packager")
    manifest = m01.run_module({"source_registry": source_registry, "capture_task_manifest": tasks, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints}, CONFIG)["outputs"]["ingestion_manifest"]
    registry = m02.run_module({"source_registry": source_registry, "ingestion_manifest": manifest, "versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["source_snapshot_registry"]
    errors = m03.run_module({"ingestion_manifest": manifest, "raw_readability_report": readable, "capture_task_manifest": tasks}, CONFIG)["outputs"]["ingestion_error_report"]
    handoff = m04.run_module({"ingestion_manifest": manifest, "source_registry": source_registry, "source_snapshot_registry": registry, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints, "ingestion_error_report": errors}, CONFIG)["outputs"]["handoff_manifest_to_phase_2"]
    assert manifest["all_attempted_tasks_accounted"] is True, "all_attempted_tasks_accounted"
    assert manifest["lineage_id"], "lineage_complete"
    assert len(registry["snapshots"]) == 1 and registry["snapshots"][0]["file_hash"] == "h1", "source_snapshot_unique"
    assert registry["snapshots"][0]["file_hash"] == versioned["records"][0]["file_hash"], "snapshot_references_hash"
    assert errors["no_silent_failure"] is True and errors["errors"][0]["error_code"] == "NO_ERROR", "critical_error_explicit"
    assert handoff["no_blocking_error_open"] is True and handoff["records"][0]["file_hash"] == "h1", "all_phase2_outputs_present"
    assert handoff["records"][0]["file_hash"], "hashes_present"


def test_s5_rejects_unregistered_source_duplicate_snapshot_and_blocking_error():
    source_registry, tasks, versioned, readable, hints = _s5_inputs()
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder")
    m04 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M04_phase2_handoff_packager")
    with pytest.raises(Exception, match="unregistered"):
        m01.run_module({"source_registry": {"sources": []}, "capture_task_manifest": tasks, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints}, CONFIG)
    with pytest.raises(Exception, match="unique"):
        m02.run_module({"source_registry": source_registry, "ingestion_manifest": {}, "versioned_raw_file_inventory": {"records": [versioned["records"][0], versioned["records"][0]]}}, CONFIG)
    bad_errors = {"errors": [{"source_id": "s1", "error_flag": True, "is_blocking": True}]}
    with pytest.raises(Exception, match="no_blocking_error_open"):
        m04.run_module({"ingestion_manifest": {}, "source_registry": source_registry, "source_snapshot_registry": {"snapshots": []}, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints, "ingestion_error_report": bad_errors}, CONFIG)


def test_P1_S1_M01_dedicated_source_registry_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    result = module.run_module({"source_registry_config": {}, "api_source_definitions": {"sources": [{"source_id": "api", "source_type": "api"}]}, "manual_source_definitions": {"sources": []}}, CONFIG)
    assert result["outputs"]["source_registry"]["sources"][0]["source_id"] == "api"


def test_P1_S1_M02_dedicated_run_config_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    result = module.run_module({"ingestion_run_config": {"run_id": "r1"}, "source_credentials_handle": {"handle_id": "h1"}, "source_calendar_config": {"calendar_id": "c1"}, "source_registry": {"sources": []}}, CONFIG)
    assert result["outputs"]["validated_ingestion_run_config"]["credentials_materialized"] is False


def test_P1_S1_M03_dedicated_availability_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    result = module.run_module({"validated_ingestion_run_config": {"run_id": "r1"}, "source_registry": {"sources": [{"source_id": "s1", "critical": True}]}, "source_calendar_config": {"calendar_id": "c1"}, "local_raw_file_paths": ["raw/s1"]}, CONFIG)
    assert result["outputs"]["source_capture_plan"]["tasks"][0]["critical"] is True


def test_P1_S2_M01_dedicated_capture_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M01_source_capture_orchestrator")
    result = module.run_module({"source_capture_plan": {"tasks": [{"task_id": "t1", "source_id": "s1", "lineage_id": "l1"}]}}, CONFIG)
    assert result["outputs"]["capture_task_manifest"]["tasks"][0]["lineage_id"] == "l1"


@pytest.mark.parametrize("module_name", [
    "P1_S2_M02_b3_cotahist_raw_fetcher", "P1_S2_M03_macro_raw_fetcher", "P1_S2_M04_benchmark_raw_fetcher", "P1_S2_M05_crypto_raw_fetcher", "P1_S2_M06_document_raw_collector",
])
def test_P1_S2_M02_M03_M04_M05_M06_dedicated_raw_oracle(module_name):
    module = importlib.import_module(f"quant_pipeline.phase_01_ingestion.modules.{module_name}")
    artifact = {"P1_S2_M02_b3_cotahist_raw_fetcher": "b3_raw_capture_inventory", "P1_S2_M03_macro_raw_fetcher": "macro_raw_capture_inventory", "P1_S2_M04_benchmark_raw_fetcher": "benchmark_raw_capture_inventory", "P1_S2_M05_crypto_raw_fetcher": "crypto_raw_capture_inventory", "P1_S2_M06_document_raw_collector": "document_raw_capture_inventory"}[module_name]
    result = module.run_module({"capture_task_manifest": {"tasks": [{"task_id": "t1", "source_id": "s1", "lineage_id": "l1", "raw_bytes": b"real-fixture", "available_at": "2024-01-01T00:00:00Z"}]}}, CONFIG)
    assert result["outputs"][artifact]["raw_preserved"] is True


def test_P1_S2_M07_dedicated_aggregate_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M07_non_b3_capture_inventory_assembler")
    inv = lambda source: {"records": [{"source_id": source, "raw_preserved": True, "cleaning_applied": False, "lineage_id": f"l-{source}"}]}
    result = module.run_module({key: inv(key) for key in ("macro_raw_capture_inventory", "benchmark_raw_capture_inventory", "crypto_raw_capture_inventory", "document_raw_capture_inventory")}, CONFIG)
    assert len(result["outputs"]["non_b3_raw_capture_inventory"]["records"]) == 4


def test_P1_S3_M01_dedicated_writer_oracle(tmp_path):
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M01_raw_artifact_writer")
    inv = {"records": [{"source_id": "s1", "raw_bytes": b"bytes", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l1"}]}
    result = module.run_module({"b3_raw_capture_inventory": inv, "non_b3_raw_capture_inventory": {"records": []}}, {**CONFIG, "artifact_root": str(tmp_path)})
    assert result["outputs"]["raw_file_inventory"]["records"][0]["path_exists"] is True


def test_P1_S3_M02_dedicated_hash_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S3_M02_hash_version_manager")
    inv = {"records": [{"artifact_id": "a1", "source_id": "s1", "raw_bytes": b"abc", "lineage_id": "l1"}]}
    result = module.run_module({"raw_file_inventory": inv, "raw_artifact_store": inv}, CONFIG)
    assert result["outputs"]["versioned_raw_file_inventory"]["records"][0]["file_hash"]


def test_P1_S4_M01_dedicated_readability_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M01_raw_readability_checker")
    result = module.run_module({"versioned_raw_file_inventory": {"records": [{"source_id": "s1", "raw_bytes": b"abc", "file_hash": "h", "lineage_id": "l1"}]}}, CONFIG)
    assert result["outputs"]["raw_readability_report"]["checks"][0]["readability_status"] == "readable"


def test_P1_S4_M02_dedicated_schema_hint_oracle():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S4_M02_raw_schema_hint_detector")
    result = module.run_module({"versioned_raw_file_inventory": {"records": [{"source_id": "s1", "raw_bytes": b"abc", "file_hash": "h", "lineage_id": "l1"}]}, "raw_readability_report": {"checks": [{"source_id": "s1", "readability_status": "readable"}]}}, CONFIG)
    assert result["outputs"]["raw_schema_hint_report"]["hints"][0]["is_clean_schema"] is False


@pytest.mark.parametrize("module_id", ["P1_S5_M01", "P1_S5_M02", "P1_S5_M03", "P1_S5_M04"])
def test_P1_S5_M01_M02_M03_M04_dedicated_manifest_oracle(module_id):
    source_registry, tasks, versioned, readable, hints = _s5_inputs()
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M01_ingestion_manifest_builder")
    manifest = m01.run_module({"source_registry": source_registry, "capture_task_manifest": tasks, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints}, CONFIG)["outputs"]["ingestion_manifest"]
    if module_id == "P1_S5_M01": assert manifest["all_attempted_tasks_accounted"]
    elif module_id == "P1_S5_M02":
        result = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder").run_module({"source_registry": source_registry, "ingestion_manifest": manifest, "versioned_raw_file_inventory": versioned}, CONFIG)
        assert result["outputs"]["source_snapshot_registry"]["snapshots"][0]["file_hash"] == "h1"
    elif module_id == "P1_S5_M03":
        result = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder").run_module({"ingestion_manifest": manifest, "raw_readability_report": readable, "capture_task_manifest": tasks}, CONFIG)
        assert result["outputs"]["ingestion_error_report"]["no_silent_failure"]
    else:
        registry = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M02_source_snapshot_registry_builder").run_module({"source_registry": source_registry, "ingestion_manifest": manifest, "versioned_raw_file_inventory": versioned}, CONFIG)["outputs"]["source_snapshot_registry"]
        errors = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M03_ingestion_error_report_builder").run_module({"ingestion_manifest": manifest, "raw_readability_report": readable, "capture_task_manifest": tasks}, CONFIG)["outputs"]["ingestion_error_report"]
        result = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S5_M04_phase2_handoff_packager").run_module({"ingestion_manifest": manifest, "source_registry": source_registry, "source_snapshot_registry": registry, "versioned_raw_file_inventory": versioned, "raw_readability_report": readable, "raw_schema_hint_report": hints, "ingestion_error_report": errors}, CONFIG)
        assert result["outputs"]["handoff_manifest_to_phase_2"]["no_blocking_error_open"]


@pytest.mark.parametrize("module_name", [
    "P1_S1_M01_source_registry_loader", "P1_S1_M02_ingestion_run_config_validator", "P1_S1_M03_source_availability_planner",
    "P1_S2_M01_source_capture_orchestrator", "P1_S2_M02_b3_cotahist_raw_fetcher", "P1_S2_M03_macro_raw_fetcher",
    "P1_S2_M04_benchmark_raw_fetcher", "P1_S2_M05_crypto_raw_fetcher", "P1_S2_M06_document_raw_collector",
    "P1_S2_M07_non_b3_capture_inventory_assembler", "P1_S3_M01_raw_artifact_writer", "P1_S3_M02_hash_version_manager",
    "P1_S4_M01_raw_readability_checker", "P1_S4_M02_raw_schema_hint_detector", "P1_S5_M01_ingestion_manifest_builder",
    "P1_S5_M02_source_snapshot_registry_builder", "P1_S5_M03_ingestion_error_report_builder", "P1_S5_M04_phase2_handoff_packager",
], ids=lambda value: value.split("_", 3)[0] + "_" + value.split("_", 3)[1] + "_" + value.split("_", 3)[2])
def test_P1_strict_negative_domain_oracle(module_name):
    module = importlib.import_module(f"quant_pipeline.phase_01_ingestion.modules.{module_name}")
    with pytest.raises(Exception):
        module.run_module({}, CONFIG)
