from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-23T00:00:00Z"}


def test_registry_rejects_nested_secrets_and_normalizes_dataset_routing():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    with pytest.raises(Exception, match="credential material"):
        module.run_module({
            "source_registry_config": {},
            "api_source_definitions": {"sources": [{
                "source_id": "fred", "source_type": "api",
                "credentials": {"api_key": "secret"},
            }]},
            "manual_source_definitions": {"sources": []},
        }, CONFIG)

    result = module.run_module({
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{
            "source_id": "fred", "source_type": "api", "credential_kind": "API_KEY",
            "credential_handle": "FRED_API_KEY",
            "datasets": [
                {"dataset_id": "cpi", "domain": "macro"},
                {"dataset_id": "gdp", "domain": "macro"},
            ],
        }]},
        "manual_source_definitions": {"sources": []},
    }, CONFIG)
    source = result["outputs"]["source_registry"]["sources"][0]
    assert source["adapter_id"] == "fred"
    assert [x["dataset_id"] for x in source["datasets"]] == ["cpi", "gdp"]
    assert all(x["domain"] == "macro" for x in source["datasets"])


def test_s1_plans_multiple_datasets_and_propagates_run_identity():
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    s2m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M01_source_capture_orchestrator")

    registry = m01.run_module({
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{
            "source_id": "fred", "source_type": "api", "credential_kind": "API_KEY",
            "credential_handle": "FRED_API_KEY",
            "datasets": [
                {"dataset_id": "cpi", "domain": "macro", "available_at": "2026-01-10T13:30:00Z"},
                {"dataset_id": "gdp", "domain": "macro", "partitions": ["2025", "2026"]},
            ],
        }]},
        "manual_source_definitions": {"sources": []},
    }, CONFIG)["outputs"]["source_registry"]
    run = m02.run_module({
        "ingestion_run_config": {"run_id": "RUN-42", "as_of_time": "2026-07-23T00:00:00Z", "contract_mode": "CAPTURE_V2"},
        "source_credentials_handle": {"handles": ["FRED_API_KEY"]},
        "source_calendar_config": {"calendar_id": "macro"},
        "source_registry": registry,
    }, CONFIG)["outputs"]["validated_ingestion_run_config"]
    plan = m03.run_module({
        "validated_ingestion_run_config": run,
        "source_registry": registry,
        "source_calendar_config": {"calendar_id": "macro"},
        "local_raw_file_paths": {},
    }, CONFIG)["outputs"]["source_capture_plan"]
    assert plan["run_id"] == "RUN-42"
    assert len(plan["tasks"]) == 3
    assert len({task["task_id"] for task in plan["tasks"]}) == 3
    assert {task["dataset_id"] for task in plan["tasks"]} == {"cpi", "gdp"}
    manifest = s2m01.run_module({"source_capture_plan": plan}, CONFIG)["outputs"]["capture_task_manifest"]
    assert manifest["run_id"] == "RUN-42"
    assert all(task["run_id"] == "RUN-42" for task in manifest["tasks"])
    assert all(task["capture_state"] == "PLANNED" for task in manifest["tasks"])


def test_same_source_multiple_captures_are_accepted_by_s2_assembler():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M07_non_b3_capture_inventory_assembler")
    def inventory(domain, records):
        return {"records": records, "attempts": [], "raw_preserved": True, "cleaning_applied": False}
    same_source = [
        {"source_id": "lse", "capture_id": "cap-1", "dataset_id": "spy", "task_id": "t1", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l1"},
        {"source_id": "lse", "capture_id": "cap-2", "dataset_id": "qqq", "task_id": "t2", "raw_preserved": True, "cleaning_applied": False, "lineage_id": "l2"},
    ]
    result = module.run_module({
        "macro_raw_capture_inventory": inventory("macro", []),
        "benchmark_raw_capture_inventory": inventory("benchmark", same_source),
        "crypto_raw_capture_inventory": inventory("crypto", []),
        "document_raw_capture_inventory": inventory("document", []),
    }, {**CONFIG, "contract_mode": "CAPTURE_V2"})["outputs"]["non_b3_raw_capture_inventory"]
    assert len(result["records"]) == 2
    assert {r["capture_id"] for r in result["records"]} == {"cap-1", "cap-2"}


def test_raw_bytes_hash_is_exact_sha256_and_capture_identity_is_present():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M03_macro_raw_fetcher")
    result = module.run_module({"capture_task_manifest": {"tasks": [{
        "task_id": "t1", "run_id": "r1", "source_id": "fred", "dataset_id": "cpi",
        "domain": "macro", "source_category": "macro", "lineage_id": "l1",
        "raw_bytes": b"abc", "available_at": "2026-01-01T00:00:00Z",
    }]}}, CONFIG)["outputs"]["macro_raw_capture_inventory"]
    record = result["records"][0]
    assert record["raw_content_sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert record["capture_id"].startswith("capture-")
    assert record["run_id"] == "r1"


class _FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}
    url = "https://example.test/data?api_key=[REDACTED]"
    requested_at = "2026-07-23T00:00:00Z"
    retrieved_at = "2026-07-23T00:00:01Z"
    retry_count = 0
    content = b'{"ok":true}'


class _FakeHttpClient:
    def request(self, method, url, **kwargs):
        assert kwargs["params"]["api_key"] == "secret-at-runtime"
        return _FakeResponse()


def test_configured_adapter_resolves_secret_at_runtime_but_does_not_persist_it():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M03_macro_raw_fetcher")
    result = module.run_module({"capture_task_manifest": {"tasks": [{
        "task_id": "t1", "run_id": "r1", "source_id": "fred", "provider": "fred",
        "adapter_id": "fred", "dataset_id": "cpi", "domain": "macro", "source_category": "macro",
        "lineage_id": "l1", "credential_handle": "FRED_API_KEY", "credential_required": True,
        "request_spec": {"url": "https://example.test/data", "params": {"series_id": "CPI"}},
        "available_at": "2026-01-01T00:00:00Z",
    }]}}, {**CONFIG, "environment": {"FRED_API_KEY": "secret-at-runtime"}, "http_client": _FakeHttpClient()})
    artifact = result["outputs"]["macro_raw_capture_inventory"]
    assert artifact["records"][0]["raw_bytes"] == b'{"ok":true}'
    serialized = repr(artifact)
    assert "secret-at-runtime" not in serialized
    assert artifact["records"][0]["source_url"].endswith("api_key=%5BREDACTED%5D") or "[REDACTED]" in artifact["records"][0]["source_url"]



def test_legacy_v1_rejects_multi_capture_plan_before_downstream_breakage():
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    m03 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M03_source_availability_planner")
    registry = m01.run_module({
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{
            "source_id": "fred", "source_type": "api",
            "datasets": [{"dataset_id": "cpi", "domain": "macro"}, {"dataset_id": "gdp", "domain": "macro"}],
        }]},
        "manual_source_definitions": {"sources": []},
    }, CONFIG)["outputs"]["source_registry"]
    run = m02.run_module({
        "ingestion_run_config": {"run_id": "RUN-LEGACY", "as_of_time": "2026-07-23T00:00:00Z"},
        "source_credentials_handle": {"handles": []},
        "source_calendar_config": {"calendar_id": "macro"},
        "source_registry": registry,
    }, CONFIG)["outputs"]["validated_ingestion_run_config"]
    assert run["contract_mode"] == "LEGACY_V1"
    with pytest.raises(Exception, match="LEGACY_V1 compatibility"):
        m03.run_module({
            "validated_ingestion_run_config": run,
            "source_registry": registry,
            "source_calendar_config": {"calendar_id": "macro"},
            "local_raw_file_paths": {},
        }, CONFIG)


def test_run_config_compares_timezone_offsets_as_instants_and_validates_iana_timezone():
    m01 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    m02 = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M02_ingestion_run_config_validator")
    registry = m01.run_module({
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{"source_id": "fred", "source_type": "api"}]},
        "manual_source_definitions": {"sources": []},
    }, CONFIG)["outputs"]["source_registry"]
    result = m02.run_module({
        "ingestion_run_config": {
            "run_id": "R1", "timezone": "America/Sao_Paulo",
            "start_time": "2026-01-01T10:00:00+02:00",
            "end_time": "2026-01-01T07:30:00-01:00",
        },
        "source_credentials_handle": {"handles": []},
        "source_calendar_config": {"calendar_id": "x"},
        "source_registry": registry,
    }, CONFIG)["outputs"]["validated_ingestion_run_config"]
    assert result["start_time"] == "2026-01-01T08:00:00Z"
    assert result["end_time"] == "2026-01-01T08:30:00Z"
    with pytest.raises(Exception, match="valid IANA timezone"):
        m02.run_module({
            "ingestion_run_config": {"run_id": "R2", "timezone": "Mars/Olympus"},
            "source_credentials_handle": {"handles": []},
            "source_calendar_config": {"calendar_id": "x"},
            "source_registry": registry,
        }, CONFIG)


def test_strict_registry_rejects_unknown_explicit_adapter_but_compat_mode_marks_it():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S1_M01_source_registry_loader")
    inputs = {
        "source_registry_config": {},
        "api_source_definitions": {"sources": [{
            "source_id": "custom", "source_type": "api", "adapter_id": "does_not_exist",
        }]},
        "manual_source_definitions": {"sources": []},
    }
    compat = module.run_module(inputs, CONFIG)["outputs"]["source_registry"]["sources"][0]
    assert compat["adapter_registered"] is False
    with pytest.raises(Exception, match="adapter_id is not registered"):
        module.run_module(inputs, {**CONFIG, "strict_adapter_ids": True})


class _TwoPageHttpClient:
    def __init__(self):
        self.calls = 0
    def request(self, method, url, **kwargs):
        self.calls += 1
        class R:
            status = 200
            headers = {"content-type": "application/json"}
            requested_at = "2026-07-23T00:00:00Z"
            retrieved_at = "2026-07-23T00:00:01Z"
            retry_count = 0
        r = R()
        if self.calls == 1:
            r.url = "https://example.test/data?page_token=[REDACTED]"
            r.content = b'{"next":"token-2","data":[1]}'
        else:
            r.url = "https://example.test/data?page_token=[REDACTED]"
            r.content = b'{"next":null,"data":[2]}'
        return r


def test_legacy_v1_rejects_paginated_multi_capture_early_but_capture_v2_accepts():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M03_macro_raw_fetcher")
    task = {
        "task_id": "t1", "run_id": "r1", "source_id": "fred", "provider": "fred",
        "adapter_id": "fred", "dataset_id": "cpi", "domain": "macro", "source_category": "macro",
        "lineage_id": "l1", "credential_handle": "FRED_API_KEY", "credential_required": True,
        "request_spec": {"url": "https://example.test/data", "pagination": {
            "type": "next_token", "token_param": "page_token", "next_token_path": "next"
        }},
    }
    with pytest.raises(Exception, match="LEGACY_V1 downstream compatibility"):
        module.run_module({"capture_task_manifest": {"tasks": [{**task, "contract_mode": "LEGACY_V1"}]}}, {
            **CONFIG, "environment": {"FRED_API_KEY": "secret"}, "http_client": _TwoPageHttpClient(),
        })
    result = module.run_module({"capture_task_manifest": {"tasks": [{**task, "contract_mode": "CAPTURE_V2"}]}}, {
        **CONFIG, "contract_mode": "CAPTURE_V2", "environment": {"FRED_API_KEY": "secret"}, "http_client": _TwoPageHttpClient(),
    })["outputs"]["macro_raw_capture_inventory"]
    assert len(result["records"]) == 2
    assert len({r["capture_id"] for r in result["records"]}) == 2


def test_sec_adapter_requires_identifying_user_agent():
    module = importlib.import_module("quant_pipeline.phase_01_ingestion.modules.P1_S2_M06_document_raw_collector")
    task = {
        "task_id": "sec1", "run_id": "r1", "source_id": "sec", "provider": "sec", "adapter_id": "sec",
        "dataset_id": "submissions", "domain": "document", "source_category": "document", "lineage_id": "l1",
        "request_spec": {"url": "https://example.test/sec"},
    }
    artifact = module.run_module({"capture_task_manifest": {"tasks": [task]}}, {**CONFIG, "http_client": _FakeHttpClient()})["outputs"]["document_raw_capture_inventory"]
    assert artifact["records"] == []
    assert len(artifact["attempts"]) == 1
    assert artifact["attempts"][0]["capture_state"] in {"FAILED_BLOCKING", "FAILED_NON_BLOCKING"}
    assert "credential" in (artifact["attempts"][0].get("error_message") or "").lower() or "user-agent" in (artifact["attempts"][0].get("error_message") or "").lower()
