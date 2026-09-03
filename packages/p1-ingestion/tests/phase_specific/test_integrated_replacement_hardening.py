from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from quant_pipeline.phase_01_ingestion.core import sanitize_url
from quant_pipeline.phase_01_ingestion.modules._module_executor import ContractValidationError


CONFIG = {"created_at": "2026-07-23T00:00:00Z", "pipeline_version": "V14.1-RC4.1"}


def _registry_input(sources):
    return {
        "source_registry_config": {"registry_id": "r"},
        "api_source_definitions": {"sources": sources},
        "manual_source_definitions": {"sources": []},
    }


def test_source_id_uniqueness_is_checked_after_canonical_normalization():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    with pytest.raises(ContractValidationError):
        module.run_module(_registry_input([
            {"source_id": 1, "source_type": "api", "source_category": "macro"},
            {"source_id": "1", "source_type": "api", "source_category": "macro"},
        ]), CONFIG)


def test_registered_adapter_alias_is_accepted_in_strict_mode():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    out = module.run_module(_registry_input([
        {"source_id": "lse-source", "source_type": "api", "source_category": "benchmark", "adapter_id": "london_strategic_edge"},
    ]), {**CONFIG, "strict_adapter_ids": True})
    source = out["outputs"]["source_registry"]["sources"][0]
    assert source["adapter_id"] == "lse"
    assert source["adapter_registered"] is True


def test_query_secret_redaction_covers_common_secret_names():
    url = sanitize_url("https://example.test/x?client_secret=a&password=b&access_token=c&ok=1")
    assert "client_secret=a" not in url and "password=b" not in url and "access_token=c" not in url
    assert "ok=1" in url
    assert url.count("%5BREDACTED%5D") == 3


def test_planner_rejects_date_only_available_at_as_contract_error_not_type_error():
    planner = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    inputs = {
        "validated_ingestion_run_config": {"run_id": "R", "contract_mode": "CAPTURE_V2", "as_of_time": "2026-07-23T00:00:00Z"},
        "source_registry": {"sources": [{"source_id": "fred", "source_type": "api", "source_category": "macro", "datasets": [{"dataset_id": "CPI", "available_at": "2026-07-22"}]}]},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {},
    }
    with pytest.raises(ContractValidationError):
        planner.run_module(inputs, CONFIG)


def test_legacy_pagination_is_rejected_during_planning_before_network():
    planner = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    inputs = {
        "validated_ingestion_run_config": {"run_id": "R", "contract_mode": "LEGACY_V1", "as_of_time": "2026-07-23T00:00:00Z"},
        "source_registry": {"sources": [{"source_id": "fred", "source_type": "api", "source_category": "macro", "datasets": [{"dataset_id": "CPI", "available_at": "2026-07-22T00:00:00Z", "request_spec": {"url": "https://example.invalid", "pagination": {"mode": "offset_total"}}}]}]},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {},
    }
    with pytest.raises(ContractValidationError, match="LEGACY_V1 cannot execute paginated"):
        planner.run_module(inputs, CONFIG)


def test_full_local_pipeline_streams_file_without_path_read_bytes(tmp_path: Path, monkeypatch):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "raw.json"
    raw.write_text('{"ok":true}', encoding="utf-8")
    original = Path.read_bytes

    def blocked(self):
        if self == raw:
            raise AssertionError("raw source was materialized with Path.read_bytes")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", blocked)
    inputs = {
        "source_registry_config": {"registry_id": "r"},
        "ingestion_run_config": {"run_id": "R", "as_of_time": "2026-07-23T00:00:00Z"},
        "source_credentials_handle": {},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {"fred": str(raw)},
        "api_source_definitions": {"sources": [{"source_id": "fred", "source_type": "file", "source_category": "macro", "format": "json", "available_at": "2026-07-22T00:00:00Z"}]},
        "manual_source_definitions": {"sources": []},
    }
    out = runner.run_phase(inputs, {**CONFIG, "artifact_root": str(tmp_path / "artifacts")})
    assert out["phase_outputs"]["handoff_manifest_to_phase_2"]["records"]


def test_provider_failure_cause_survives_to_final_error_report(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    inputs = {
        "source_registry_config": {"registry_id": "r"},
        "ingestion_run_config": {"run_id": "R", "contract_mode": "CAPTURE_V2", "as_of_time": "2026-07-23T00:00:00Z"},
        "source_credentials_handle": {"allowed_handles": ["FRED_API_KEY"]},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {},
        "api_source_definitions": {"sources": [{
            "source_id": "fred", "source_type": "api", "source_category": "macro", "adapter_id": "fred",
            "credential_kind": "API_KEY", "credential_handle": "FRED_API_KEY",
            "datasets": [{"dataset_id": "CPI", "available_at": "2026-07-22T00:00:00Z", "request_spec": {"url": "https://example.invalid"}}],
        }]},
        "manual_source_definitions": {"sources": []},
    }
    out = runner.run_phase(inputs, {**CONFIG, "environment": {}, "artifact_root": str(tmp_path / "artifacts")})
    error = out["phase_outputs"]["ingestion_error_report"]["errors"][0]
    assert error["error_code"] == "PROVIDER_UNAVAILABLE"
    assert "credential" in error["error_message"].lower()


def test_runner_does_not_mutate_caller_config(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "raw.json"; raw.write_text('{"ok":1}')
    inputs = {
        "source_registry_config": {"registry_id": "r"},
        "ingestion_run_config": {"run_id": "R"},
        "source_credentials_handle": {},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {"fred": str(raw)},
        "api_source_definitions": {"sources": [{"source_id": "fred", "source_type": "file", "source_category": "macro", "format": "json"}]},
        "manual_source_definitions": {"sources": []},
    }
    config = {**CONFIG, "artifact_root": str(tmp_path / "artifacts")}
    before = dict(config)
    runner.run_phase(inputs, config)
    assert config == before


def _base_local_inputs(raw: Path, *, run_cfg=None, available_at="2026-07-22T00:00:00Z"):
    return {
        "source_registry_config": {"registry_id": "r"},
        "ingestion_run_config": {"run_id": "R", "as_of_time": "2026-07-23T00:00:00Z", **(run_cfg or {})},
        "source_credentials_handle": {},
        "source_calendar_config": {"calendar_id": "g"},
        "local_raw_file_paths": {"fred": str(raw)},
        "api_source_definitions": {"sources": [{
            "source_id": "fred", "source_type": "file", "source_category": "macro",
            "format": "json", "available_at": available_at,
        }]},
        "manual_source_definitions": {"sources": []},
    }


def test_future_relative_to_as_of_is_never_captured_or_handed_off(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "future.json"; raw.write_text('{"future":true}')
    inputs = _base_local_inputs(raw, available_at="2026-08-01T00:00:00Z")
    out = runner.run_phase(inputs, {**CONFIG, "artifact_root": str(tmp_path / "artifacts")})
    assert out["phase_outputs"]["handoff_manifest_to_phase_2"]["records"] == []
    errors = out["phase_outputs"]["ingestion_error_report"]["errors"]
    assert errors and errors[0]["error_code"] == "FUTURE_RELATIVE_TO_AS_OF"


def test_allow_partial_success_false_blocks_handoff(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "bad.json"; raw.write_text('{bad json')
    inputs = _base_local_inputs(raw, run_cfg={"allow_partial_success": False})
    with pytest.raises(ContractValidationError, match="allow_partial_success=false"):
        runner.run_phase(inputs, {**CONFIG, "artifact_root": str(tmp_path / "artifacts")})


def test_semantic_artifact_ids_are_replay_stable_without_created_at(tmp_path: Path):
    runner = importlib.import_module("quant_pipeline.phase_01_ingestion.runner")
    raw = tmp_path / "raw.json"; raw.write_text('{"ok":1}')
    inputs = _base_local_inputs(raw)
    cfg1 = {"pipeline_version": "V14.1-RC4.1", "artifact_root": str(tmp_path / "a1")}
    cfg2 = {"pipeline_version": "V14.1-RC4.1", "artifact_root": str(tmp_path / "a2")}
    a = runner.run_phase(inputs, cfg1)["phase_outputs"]
    b = runner.run_phase(inputs, cfg2)["phase_outputs"]
    assert a["raw_file_inventory"]["artifact_id"] == b["raw_file_inventory"]["artifact_id"]
    assert a["source_snapshot_registry"]["artifact_id"] == b["source_snapshot_registry"]["artifact_id"]
    assert a["handoff_manifest_to_phase_2"]["artifact_id"] == b["handoff_manifest_to_phase_2"]["artifact_id"]


def test_http_client_rejects_non_read_only_methods_and_non_http_schemes():
    from quant_pipeline.phase_01_ingestion.transport.http_client import HttpClient, TransportError
    client = HttpClient()
    with pytest.raises(TransportError, match="method is not allowed"):
        client.request("DELETE", "https://example.invalid/x")
    with pytest.raises(TransportError, match="scheme is not allowed"):
        client.request("GET", "file:///tmp/x")


def test_unsupported_parallel_concurrency_is_rejected_explicitly():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    with pytest.raises(ContractValidationError, match="max_workers > 1"):
        module.run_module({
            "ingestion_run_config": {"run_id": "R", "concurrency_policy": {"max_workers": 2}},
            "source_credentials_handle": {},
            "source_calendar_config": {"calendar_id": "g"},
            "source_registry": {"sources": []},
        }, CONFIG)


def test_http_client_blocks_private_literal_and_localhost_before_network():
    from quant_pipeline.phase_01_ingestion.transport.http_client import HttpClient, TransportError
    client = HttpClient(allow_insecure_http=True)
    for url in ("http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/latest"):
        with pytest.raises(TransportError, match="blocked"):
            client.request("GET", url)


def test_provider_request_budget_is_enforced_before_extra_request():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M03_macro_raw_fetcher")

    class FakeHttp:
        def request(self, *args, **kwargs):
            raise AssertionError("provider budget should block before network")

    task = {
        "task_id": "t1", "run_id": "R", "source_id": "fred", "provider": "fred",
        "adapter_id": "fred", "dataset_id": "CPI", "domain": "macro",
        "source_category": "macro", "lineage_id": "l1", "contract_mode": "CAPTURE_V2",
        "request_spec": {"url": "https://example.test/data"},
    }
    out = module.run_module(
        {"capture_task_manifest": {"tasks": [task]}},
        {**CONFIG, "http_client": FakeHttp(), "provider_budgets": {"fred": {"max_requests": 0}}},
    )["outputs"]["macro_raw_capture_inventory"]
    assert out["records"] == []
    assert out["attempts"][0]["error_code"] == "QUOTA_EXHAUSTED"
