from __future__ import annotations

import json

from quant_pipeline.phase_02_quality_pit.modules._s1_core import read_artifact_rows


def _descriptor(provider: str) -> dict:
    return {
        "provider": provider,
        "source_id": provider,
        "source_name": provider.upper(),
        "source_type": "api",
        "declared_available_at": "2026-07-30T00:00:00Z",
        "ingested_at": "2026-07-30T00:00:01Z",
        "lineage_id": f"lineage-{provider}",
    }


def test_alpha_vantage_news_is_materialized_as_p2_documents(tmp_path):
    path = tmp_path / "news.bin"
    path.write_text(json.dumps({
        "feed": [{
            "title": "Earnings released",
            "summary": "Company released earnings.",
            "url": "https://example.test/news/1",
            "time_published": "20260729T120000",
        }]
    }), encoding="utf-8")

    rows = read_artifact_rows(path, "json", {}, _descriptor("alpha_vantage_news"))

    assert len(rows) == 1
    assert rows[0]["record_domain"] == "DOCUMENT"
    assert rows[0]["document_type"] == "news"
    assert rows[0]["available_at"] == "2026-07-29T12:00:00Z"
    assert rows[0]["lineage_id"] == "lineage-alpha_vantage_news"


def test_sec_recent_filings_are_materialized_as_p2_documents(tmp_path):
    path = tmp_path / "sec.bin"
    path.write_text(json.dumps({
        "cik": "0000320193",
        "filings": {"recent": {
            "form": ["10-Q"],
            "accessionNumber": ["0000320193-26-000001"],
            "filingDate": ["2026-07-29"],
            "reportDate": ["2026-06-30"],
            "primaryDocument": ["quarterly.htm"],
        }}
    }), encoding="utf-8")

    rows = read_artifact_rows(path, "json", {}, _descriptor("sec"))

    assert len(rows) == 1
    assert rows[0]["record_domain"] == "DOCUMENT"
    assert rows[0]["document_type"] == "filing"
    assert rows[0]["reference_date"] == "2026-06-30"
    assert "Archives/edgar/data/320193/000032019326000001/quarterly.htm" in rows[0]["source_url"]
