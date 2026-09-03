from __future__ import annotations

import hashlib
import importlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2026-07-23T12:00:00Z",
}


def mod(name: str):
    return importlib.import_module(f"quant_pipeline.phase_02_quality_pit.modules.{name}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_inputs(path: Path, *, readability_status: str = "readable", error_flag: bool = False, is_blocking: bool = False):
    digest = sha256(path)
    size = path.stat().st_size
    handoff = {
        "handoff_artifact_id": "handoff-1",
        "ingestion_run_id": "run-1",
        "source_id": "source-1",
        "source_name": "Source One",
        "source_type": "file",
        "source_category": "market",
        "raw_artifact_id": "raw-1",
        "raw_artifact_path": str(path),
        "file_hash": digest,
        "file_size_bytes": size,
        "ingested_at": "2026-07-23T11:00:00Z",
        "source_reference_date": "2026-07-22",
        "declared_available_at": "2026-07-23T10:59:00Z",
        "readability_status": readability_status,
        "schema_hint_id": "hint-1",
        "error_flag": error_flag,
        "warning_flag": readability_status == "warning",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": "lineage-1",
    }
    snapshot = {
        **handoff,
        "artifact_id": "snapshot-1",
        "created_at": "2026-07-23T11:00:00Z",
    }
    return {
        "handoff_manifest_to_phase_2": {"records": [handoff]},
        "source_registry": {"records": [{"source_id": "source-1", "artifact_id": "registry-1"}]},
        "raw_file_inventory": {"records": [{
            "source_id": "source-1",
            "raw_artifact_id": "raw-1",
            "raw_artifact_path": str(path),
            "file_hash": digest,
            "file_size_bytes": size,
        }]},
        "source_snapshot_registry": {"records": [snapshot]},
        "raw_readability_report": {"records": [{
            "source_id": "source-1",
            "raw_artifact_id": "raw-1",
            "readability_status": readability_status,
        }]},
        "raw_schema_hint_report": {"records": [{"schema_hint_id": "hint-1"}]},
        "ingestion_error_report": {"records": [{
            "source_id": "source-1",
            "ingestion_run_id": "run-1",
            "error_flag": error_flag,
            "is_blocking": is_blocking,
            "error_severity": "blocking" if is_blocking else ("warning" if error_flag else "none"),
            "error_code": "TEST" if error_flag else "NO_ERROR",
            "error_message": "test" if error_flag else "none",
        }]},
    }


def run_s1(inputs: dict, config: dict):
    validated = mod("P2_S1_M01_phase1_handoff_validator").run_module(inputs, config)["outputs"]["validated_phase1_handoff_bundle"]
    materialized = mod("P2_S1_M02_raw_artifact_reader").run_module(
        {"validated_phase1_handoff_bundle": validated}, config
    )["outputs"]["raw_artifact_read_bundle"]
    quality = mod("P2_S1_M03_source_quality_panel_builder").run_module(
        {
            "validated_phase1_handoff_bundle": validated,
            "raw_readability_report": inputs["raw_readability_report"],
            "ingestion_error_report": inputs["ingestion_error_report"],
        },
        config,
    )["outputs"]["source_quality_panel"]
    return validated, materialized, quality


@pytest.mark.parametrize(
    ("suffix", "content", "expected_rows"),
    [
        (".csv", "symbol,price\nAAA,10\nBBB,20\n", 2),
        (".json", json.dumps([{"symbol": "AAA", "price": 10}, {"symbol": "BBB", "price": 20}]), 2),
        (".jsonl", '{"symbol":"AAA","price":10}\n{"symbol":"BBB","price":20}\n', 2),
    ],
)
def test_s1_reads_real_artifacts_and_preserves_provenance(tmp_path: Path, suffix: str, content: str, expected_rows: int):
    path = tmp_path / f"raw{suffix}"
    path.write_text(content, encoding="utf-8")
    inputs = make_inputs(path)
    config = {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True}

    validated, materialized, quality = run_s1(inputs, config)

    assert validated["validated"] is True
    assert validated["hashes_match"] is True
    assert materialized["rows_materialized"] == expected_rows
    assert materialized["physical_hashes_verified"] == 1
    assert materialized["lineage_preserved"] is True
    assert all(row["source_id"] == "source-1" for row in materialized["records"])
    assert [row["_provenance"]["raw_row_number"] for row in materialized["records"]] == list(range(1, expected_rows + 1))
    assert all(row["_provenance"]["physical_hash_verified"] is True for row in materialized["records"])
    assert quality["quality_score"] == 1.0
    assert quality["quality_status"] == "PASS"


def test_s1_detects_physical_hash_drift_after_metadata_validation(tmp_path: Path):
    path = tmp_path / "raw.csv"
    path.write_text("symbol,price\nAAA,10\n", encoding="utf-8")
    inputs = make_inputs(path)
    config = {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True}

    validated = mod("P2_S1_M01_phase1_handoff_validator").run_module(inputs, config)["outputs"]["validated_phase1_handoff_bundle"]
    path.write_text("symbol,price\nAAA,999\n", encoding="utf-8")

    with pytest.raises(Exception, match="PHYSICAL_HASH_MISMATCH|FILE_SIZE_MISMATCH"):
        mod("P2_S1_M02_raw_artifact_reader").run_module(
            {"validated_phase1_handoff_bundle": validated}, config
        )


def test_s1_blocks_declared_hash_mismatch_before_file_read(tmp_path: Path):
    path = tmp_path / "raw.csv"
    path.write_text("symbol,price\nAAA,10\n", encoding="utf-8")
    inputs = make_inputs(path)
    inputs["source_snapshot_registry"]["records"][0]["file_hash"] = "0" * 64

    with pytest.raises(Exception, match="hashes_match"):
        mod("P2_S1_M01_phase1_handoff_validator").run_module(inputs, CONFIG)


def test_s1_quality_is_evidence_based_for_warning_and_blocking_error(tmp_path: Path):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps([{"x": 1}]), encoding="utf-8")

    warning_inputs = make_inputs(path, readability_status="warning")
    _, _, warning_quality = run_s1(
        warning_inputs,
        {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True},
    )
    assert warning_quality["quality_score"] < 1.0
    assert warning_quality["quality_status"] == "WARN"
    assert "READABILITY_WARNING" in warning_quality["quality_reasons"]

    blocking_inputs = make_inputs(path, error_flag=True, is_blocking=True)
    _, _, blocking_quality = run_s1(
        blocking_inputs,
        {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True},
    )
    assert blocking_quality["quality_score"] == 0.0
    assert blocking_quality["quality_status"] == "BLOCK"
    assert "BLOCKING_INGESTION_ERROR" in blocking_quality["quality_reasons"]


def test_s1_legacy_descriptor_mode_is_explicit_and_does_not_fake_physical_verification():
    legacy = {
        "records": [{
            "source_id": "s1",
            "source_name": "Source 1",
            "source_type": "api",
            "file_hash": "legacy-hash",
            "readability_status": "readable",
            "declared_available_at": "2024-01-01T00:00:00Z",
            "lineage_id": "l1",
        }]
    }
    result = mod("P2_S1_M02_raw_artifact_reader").run_module(
        {"validated_phase1_handoff_bundle": legacy}, CONFIG
    )["outputs"]["raw_artifact_read_bundle"]
    assert result["records"][0]["_provenance"]["materialization_mode"] == "descriptor_compat"
    assert result["records"][0]["_provenance"]["physical_hash_verified"] is False
    assert result["physical_hashes_verified"] == 0


def test_s1_strict_mode_rejects_missing_physical_path():
    legacy = {
        "records": [{
            "source_id": "s1",
            "file_hash": "legacy-hash",
            "readability_status": "readable",
            "declared_available_at": "2024-01-01T00:00:00Z",
            "lineage_id": "l1",
        }]
    }
    with pytest.raises(Exception, match="ARTIFACT_PATH_MISSING"):
        mod("P2_S1_M02_raw_artifact_reader").run_module(
            {"validated_phase1_handoff_bundle": legacy},
            {**CONFIG, "strict_physical_validation": True},
        )


def _b3_record(record_type: str, fields: dict[str, str] | None = None) -> bytes:
    fields = fields or {}
    line = bytearray(b" " * 245)

    def put(start: int, end: int, value: str, *, right: bool = False):
        width = end - start
        text = str(value)
        text = text.rjust(width, "0") if right else text.ljust(width)
        assert len(text) == width
        line[start:end] = text.encode("latin-1")

    put(0, 2, record_type)
    if record_type == "00":
        put(2, 15, "COTAHIST.2024")
        put(15, 23, "BOVESPA")
        put(23, 31, "20240102")
    elif record_type == "01":
        put(2, 10, fields.get("date", "20240101"))
        put(10, 12, "02")
        put(12, 24, fields.get("symbol", "PETR4"))
        put(24, 27, fields.get("market_type", "010"), right=True)
        put(27, 39, "PETROLEO")
        put(39, 49, "ON")
        put(52, 56, "BRL")
        for start, value in ((56, "10000"), (69, "10500"), (82, "9900"), (95, "10100"), (108, "10200"), (121, "10100"), (134, "10300")):
            put(start, start + 13, value, right=True)
        put(147, 152, "10", right=True)
        put(152, 170, "1000", right=True)
        put(170, 188, "1020000", right=True)
        if fields.get("strike"):
            put(188, 201, fields["strike"], right=True)
            put(202, 210, fields.get("expiration", "20241220"))
        put(210, 217, "1", right=True)
    elif record_type == "99":
        put(2, 15, "COTAHIST.2024")
        put(15, 23, "BOVESPA")
        put(23, 31, "20240102")
        put(31, 42, "3", right=True)
    return bytes(line)


def test_s1_reads_b3_cotahist_bin_by_declared_dataset_and_preserves_market_fields(tmp_path: Path):
    path = tmp_path / "cotahist-2024.bin"
    path.write_bytes(_b3_record("00") + _b3_record("01") + _b3_record("99"))
    inputs = make_inputs(path)
    for envelope in (inputs["handoff_manifest_to_phase_2"], inputs["source_snapshot_registry"]):
        envelope["records"][0].update({"source_category": "b3", "dataset": "cotahist"})
    config = {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True}

    _, materialized, _ = run_s1(inputs, config)

    assert materialized["formats_seen"] == ["b3_cotahist"]
    assert materialized["rows_materialized"] == 1
    row = materialized["records"][0]
    assert row["record_domain"] == "UNDERLYING"
    assert row["underlying"] == "PETR4"
    assert row["date"] == "2024-01-01"
    assert row["close"] == 102.0
    assert row["_provenance"]["physical_hash_verified"] is True


def test_s1_rejects_malformed_b3_record_instead_of_treating_binary_as_text(tmp_path: Path):
    path = tmp_path / "cotahist-2024.bin"
    path.write_bytes(b"01" + b" " * 20)
    inputs = make_inputs(path)
    inputs["handoff_manifest_to_phase_2"]["records"][0].update({"source_category": "b3", "dataset": "cotahist"})
    with pytest.raises(Exception, match="B3_RECORD_LENGTH"):
        run_s1(inputs, {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True})


def test_s1_decodes_alpaca_option_snapshot_payload_without_network(tmp_path: Path):
    path = tmp_path / "alpaca.json"
    path.write_text(json.dumps({"snapshots": {"AAPL240119C00100000": {"latestQuote": {"bp": 1.1, "ap": 1.3, "t": "2024-01-02T15:00:00Z"}}}}), encoding="utf-8")
    from quant_pipeline.phase_02_quality_pit.modules._s1_core import read_artifact_rows

    rows = read_artifact_rows(path, "json", {}, {"provider": "alpaca", "available_at": "2024-01-02T15:00:00Z"})
    assert rows[0]["record_domain"] == "OPTION_QUOTE"
    assert rows[0]["expiration_date"] == "2024-01-19"
    assert rows[0]["strike"] == 100.0


def test_s1_decodes_lse_underlying_and_option_candles_without_inventing_bid_ask(tmp_path: Path):
    path = tmp_path / "lse-candles.json"
    path.write_text(json.dumps({
        "options": [{"ticker": "AAPL260702P00110000"}],
        "underlying_candles": [{"symbol": "AAPL", "timestamp": "2026-06-30T00:00:00Z", "close": 195.0, "volume": 100}],
        "option_candles": [{"ticker": "AAPL260702P00110000", "underlying": "AAPL", "expiry": "2026-07-02", "contract_type": "put", "strike": 110, "minute": "2026-06-30T00:00:00Z", "close": 2.5, "volume": 10}],
    }), encoding="utf-8")
    from quant_pipeline.phase_02_quality_pit.modules._s1_core import read_artifact_rows

    rows = read_artifact_rows(path, "json", {}, {"provider": "lse", "available_at": "2026-06-30T00:00:00Z"})
    assert {row["record_domain"] for row in rows} == {"UNDERLYING", "OPTION_QUOTE"}
    option = next(row for row in rows if row["record_domain"] == "OPTION_QUOTE")
    assert option["last_price"] == 2.5
    assert "bid" not in option and "ask" not in option


def test_s1_classifies_b3_option_market_without_inventing_underlying(tmp_path: Path):
    path = tmp_path / "cotahist-options.bin"
    path.write_bytes(_b3_record("00") + _b3_record("01", {"market_type": "070", "strike": "10000"}) + _b3_record("99"))
    inputs = make_inputs(path)
    inputs["handoff_manifest_to_phase_2"]["records"][0].update({"source_category": "b3", "dataset": "cotahist"})
    _, materialized, _ = run_s1(inputs, {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True})
    row = materialized["records"][0]
    assert row["record_domain"] == "OPTION_QUOTE"
    assert row["option_type"] == "CALL"
    assert row["underlying"] is None
    assert row["strike"] == 100.0


def test_s1_applies_versioned_b3_option_underlying_map(tmp_path: Path):
    path = tmp_path / "cotahist-options.bin"
    path.write_bytes(_b3_record("00") + _b3_record("01", {"market_type": "070", "strike": "10000"}) + _b3_record("99"))
    inputs = make_inputs(path)
    inputs["handoff_manifest_to_phase_2"]["records"][0].update({"source_category": "b3", "dataset": "cotahist"})
    _, materialized, _ = run_s1(inputs, {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True, "strict_option_underlying_mapping": True, "option_underlying_map": {"PETR4": "PETR4"}})
    assert materialized["records"][0]["underlying"] == "PETR4"


def test_s1_reads_b3_cotahist_zip_member(tmp_path: Path):
    txt = _b3_record("00") + _b3_record("01") + _b3_record("99")
    path = tmp_path / "COTAHIST_A2024.ZIP"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("COTAHIST_A2024.TXT", txt)
    inputs = make_inputs(path)
    for envelope in (inputs["handoff_manifest_to_phase_2"], inputs["source_snapshot_registry"]):
        envelope["records"][0].update({"source_category": "b3", "dataset": "cotahist", "format": "b3_cotahist"})
    _, materialized, _ = run_s1(inputs, {**CONFIG, "allowed_roots": [str(tmp_path)], "strict_physical_validation": True})
    assert materialized["rows_materialized"] == 1
    assert materialized["records"][0]["underlying"] == "PETR4"


def test_s1_strict_mode_rejects_missing_reference_rows(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    path.write_text('{"symbol":"AAA"}\n', encoding="utf-8")
    inputs = make_inputs(path)
    inputs["source_snapshot_registry"]["records"] = []
    with pytest.raises(Exception, match="SNAPSHOT_REFERENCE_MISSING"):
        mod("P2_S1_M01_phase1_handoff_validator").run_module(
            inputs, {**CONFIG, "strict_physical_validation": True}
        )


def test_fred_static_is_explicitly_not_vintage_safe(tmp_path: Path):
    from quant_pipeline.phase_02_quality_pit.modules._s1_core import read_artifact_rows
    path = tmp_path / "fred.json"
    path.write_text(json.dumps({"id": "GDP", "observations": [{"date": "2026-01-01", "value": "1.0"}]}), encoding="utf-8")
    rows = read_artifact_rows(
        path,
        "json",
        {},
        {"provider": "fred", "available_at": "2026-07-31T00:00:00Z", "lineage_id": "fred-1"},
    )
    assert rows[0]["source_family"] == "FRED_STATIC_EXPORT"
    assert rows[0]["strict_historical_pit_eligible"] is False
