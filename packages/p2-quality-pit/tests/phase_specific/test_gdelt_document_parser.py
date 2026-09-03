from __future__ import annotations

from quant_pipeline.phase_02_quality_pit.modules._s1_core import _decode_option_payload


def test_gdelt_articles_materialize_point_in_time_documents() -> None:
    result = _decode_option_payload(
        {
            "articles": [
                {
                    "url": "https://example.test/article-1",
                    "title": "A headline",
                    "seendate": "20260717T001500Z",
                    "domain": "example.test",
                    "language": "English",
                }
            ]
        },
        {
            "provider": "gdelt",
            "source_id": "gdelt",
            "source_type": "file",
            "available_at": "2026-08-01T00:00:00Z",
            "retrieved_at": "2026-08-01T00:00:00Z",
        },
    )
    assert len(result) == 1
    assert result[0]["record_domain"] == "DOCUMENT"
    assert result[0]["document_id"] == "https://example.test/article-1"
    assert result[0]["available_at"] == "2026-07-17T00:15:00Z"
    assert result[0]["source_name"] == "example.test"


def test_unknown_gdelt_article_rows_are_rejected_without_fabrication() -> None:
    result = _decode_option_payload(
        {"articles": [None, "not-a-record", {}]},
        {"provider": "gdelt", "source_id": "gdelt", "available_at": "2026-08-01T00:00:00Z"},
    )
    assert result == []
