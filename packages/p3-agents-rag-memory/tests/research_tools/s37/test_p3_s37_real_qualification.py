"""Adversarial tests for the real local P3.S37 qualification runner."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
from datetime import UTC, timedelta
from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.catalog import (
    MacroSeriesReleaseCatalogBuilder,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.factory import (
    create_macro_runtime_bundle,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.macro.types import (
    OutcomeStatus,
)

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "tools" / "research_tools" / "s37" / "qualify_p3_s37_real.py"
SPEC = importlib.util.spec_from_file_location("p3_s37_real_qualification", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _real_runtime_without_context():
    rows, hashes, _ = MODULE._load_real_rows()
    catalog, _, empty_registry = MacroSeriesReleaseCatalogBuilder().build(
        snapshot_id=MODULE.SNAPSHOT_ID,
        artifacts={"clean_macro_us_panel": rows, "clean_macro_br_panel": ()},
        asset_context_registry=(),
    )
    return create_macro_runtime_bundle(
        MODULE.LocalFREDBoundary(rows, hashes), catalog, empty_registry
    )


def test_real_local_capture_is_vintage_wide_and_hash_verified() -> None:
    rows, hashes, paths = MODULE._load_real_rows()
    assert rows
    assert len(hashes) == len(paths) == 5
    assert all(len(value) == 64 for value in hashes)
    assert all(str(row["source_artifact_id"]).startswith("sha256:") for row in rows)
    assert all(str(row["lineage_id"]).startswith("sha256:") for row in rows)
    assert not any("fixtures" in path.lower() for path in paths)
    assert {str(row["pit_status"]) for row in rows} == {"DATE_LEVEL_PIT_VALIDATED"}
    assert len({(row["series_id"], row["observation_date"]) for row in rows}) < len(rows)


def test_real_s37_qualification_is_qualified_and_deterministic() -> None:
    result = MODULE.qualify()
    assert result["source"]["fixture_used"] is False
    assert result["source"]["fred_output_type"] == 2
    assert result["source"]["fred_initial_release_only"] is False
    assert result["checks"]["future_data_rejected"] is True
    assert result["checks"]["vintage_history_proved"] is True
    assert result["checks"]["asset_context_registry_proved"] is True
    assert result["checks"]["request_response_hashes_verified"] is True
    assert result["checks"]["source_artifact_id_preserved"] is True
    assert result["checks"]["lineage_preserved"] is True
    assert result["checks"]["missing_vintage_blocks"] is True
    assert result["checks"]["duplicate_qualification_rejected"] is True
    assert result["outputs_digest"]
    assert result["status"] == "QUALIFIED_LOCAL"
    assert all(status == "QUALIFIED_LOCAL" for status in result["module_status"].values())
    assert result["residual_blockers"] == []
    assert not [
        item
        for item in result["capability_matrix"]
        if item["data_status"] in {"DEGRADED", "BLOCKED_UPSTREAM"}
        or item["runtime_outcome"] in {"DEGRADED", "BLOCKED_UPSTREAM"}
    ]
    assert result["source"]["lse_inventory"]["asset_macro_context_registry_present"] is True
    assert result["source"]["fred_vintage_capture_receipt"]["api_key_persisted"] is False


def test_future_data_is_rejected_at_the_pit_boundary() -> None:
    rows, hashes, _ = MODULE._load_real_rows()
    earliest = min(
        MODULE.datetime.fromisoformat(str(row["available_at"]).replace("Z", "+00:00"))
        for row in rows
    )
    batch = MODULE.LocalFREDBoundary(rows, hashes).query(
        "clean_macro_us_panel",
        decision_time=earliest - timedelta(seconds=1),
    )
    assert not batch.rows
    assert batch.records_rejected_future > 0


def test_unproven_daily_pit_is_rejected() -> None:
    rows, hashes, _ = MODULE._load_real_rows()
    row = dict(rows[0])
    row["pit_status"] = "DATE_LEVEL_PIT_UNPROVEN"
    batch = MODULE.LocalFREDBoundary((row,), hashes).query(
        "clean_macro_us_panel",
        decision_time=MODULE.QUALIFICATION_DECISION_TIME,
    )
    assert not batch.rows
    assert batch.records_rejected_missing_time == 1


def test_absent_asset_registry_remains_empty_valid() -> None:
    runtime = _real_runtime_without_context()
    result = asyncio.run(
        runtime.execute(
            MODULE.TOOL_ID,
            "get_asset_context",
            {"asset_id": "SPY", "research_mode": "CONTEXT", "max_factors": 20},
            MODULE._context(MODULE.QUALIFICATION_DECISION_TIME, "s37-empty-registry"),
        )
    )
    assert result.outcome_status is OutcomeStatus.EMPTY_VALID
    assert not result.records


def test_absent_vintage_history_blocks_release_snapshot() -> None:
    rows, hashes, _ = MODULE._load_real_rows()
    unique: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (str(row["series_id"]), str(row["observation_date"]))
        if key not in unique:
            item = dict(row)
            item.pop("vintage_date", None)
            item.pop("revision_id", None)
            unique[key] = item
    plain_rows = tuple(unique.values())
    catalog, _, registry = MacroSeriesReleaseCatalogBuilder().build(
        snapshot_id=MODULE.SNAPSHOT_ID,
        artifacts={"clean_macro_us_panel": plain_rows, "clean_macro_br_panel": ()},
        asset_context_registry=(),
    )
    runtime = create_macro_runtime_bundle(
        MODULE.LocalFREDBoundary(plain_rows, hashes), catalog, registry
    )
    result = asyncio.run(
        runtime.execute(
            MODULE.TOOL_ID,
            "get_release_snapshot",
            {
                "series_id": "CPIAUCSL",
                "vintage_policy": "LATEST_KNOWN_AT_DECISION_TIME",
                "research_mode": "VINTAGE_ANALYSIS",
                "max_records": 20,
            },
            MODULE._context(MODULE.QUALIFICATION_DECISION_TIME, "s37-missing-vintage"),
        )
    )
    assert result.outcome_status is OutcomeStatus.BLOCKED_UPSTREAM


def test_altered_content_is_rejected_by_receipt_hash(tmp_path, monkeypatch) -> None:
    receipt = json.loads(MODULE.VINTAGE_CAPTURE_RECEIPT.read_text(encoding="utf-8"))
    item = receipt["series_receipts"][0]
    source = ROOT / item["artifact_path"]
    raw_root = tmp_path / "raw"
    artifact_dir = raw_root / item["response"]["sha256"]
    artifact_dir.mkdir(parents=True)
    target = artifact_dir / "response.json"
    shutil.copyfile(source, target)
    target.write_bytes(target.read_bytes() + b"tampered")
    monkeypatch.setattr(MODULE, "VINTAGE_RAW_ROOT", raw_root)
    monkeypatch.setattr(MODULE, "VINTAGE_CAPTURE_RECEIPT", tmp_path / "receipt.json")
    (tmp_path / "receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    try:
        MODULE._load_real_rows()
    except RuntimeError as exc:
        assert "not covered by the capture receipt" in str(exc)
    else:
        raise AssertionError("tampered FRED content was accepted")
