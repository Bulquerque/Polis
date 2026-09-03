from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

MODULE = importlib.import_module(
    "quant_pipeline.phase_02_quality_pit.modules.P2_S5_M01_context_document_event_cleaner"
)
CONFIG = {
    "pipeline_version": "V14.1-RC4.1",
    "created_at": "2024-06-01T00:00:00Z",
}


def run(rows, quality_rows=None):
    return MODULE.run_module(
        {
            "identifier_harmonized_bundle": {"records": rows},
            "source_quality_panel": {"records": quality_rows or []},
        },
        CONFIG,
    )["outputs"]


def test_document_uses_real_source_quality_and_no_fixture_defaults():
    outputs = run(
        [
            {
                "source_id": "news-1",
                "source_name": "News Source",
                "record_domain": "DOCUMENT",
                "document_type": "news",
                "document_title": "Real title",
                "document_text_or_path": "Real body",
                "reference_date": "2024-05-31",
                "available_at": "2024-05-31T12:00:00Z",
                "ingested_at": "2024-05-31T12:00:10Z",
                "language": "en",
                "lineage_id": "lineage-news-1",
            }
        ],
        [
            {
                "source_id": "news-1",
                "source_name": "News Source",
                "source_type": "api",
                "quality_score": 0.42,
                "readability_status": "readable",
                "error_flag": False,
                "warning_flag": True,
            }
        ],
    )

    document = outputs["clean_document_panel"]["records"][0]
    assert document["source_quality_score"] == 0.42
    assert document["source_quality_status"] == "known"
    assert document["language"] == "en"
    assert document["document_title"] == "Real title"
    assert "fixture" not in repr(outputs).lower()
    assert "2024-01-01" not in repr(outputs)


def test_missing_quality_is_explicitly_unknown_not_perfect():
    outputs = run(
        [
            {
                "source_id": "s1",
                "record_domain": "DOCUMENT",
                "available_at": "2024-05-31T12:00:00Z",
            }
        ]
    )
    document = outputs["clean_document_panel"]["records"][0]
    assert document["source_quality_score"] == 0.0
    assert document["source_quality_status"] == "unknown"
    assert document["language"] == "und"
    assert document["cleaning_status"] == "degraded"


def test_document_derives_honest_context_and_publication_event_for_legacy_compatibility():
    outputs = run(
        [
            {
                "source_id": "s1",
                "document_type": "document",
                "available_at": "2024-05-31T12:00:00Z",
                "lineage_id": "l1",
            }
        ]
    )

    context = outputs["clean_context_source_panel"]["records"]
    documents = outputs["clean_document_panel"]["records"]
    events = outputs["clean_event_reference_panel"]["records"]

    assert len(context) == 1
    assert context[0]["context_origin"] == "document_source"
    assert len(documents) == 1
    assert len(events) == 1
    assert events[0]["event_type"] == "document_publication"
    assert events[0]["event_origin"] == "derived_document_publication"
    assert events[0]["document_id"] == documents[0]["document_id"]


def test_event_preserves_historical_decision_time():
    outputs = run([{
        "source_id": "calendar-1",
        "record_domain": "EVENT",
        "event_id": "event-1",
        "available_at": "2024-05-31T12:00:00Z",
        "decision_time": "2024-05-31T12:00:00Z",
    }])
    assert outputs["clean_event_reference_panel"]["records"][0]["decision_time"] == "2024-05-31T12:00:00Z"


def test_operational_corporate_action_is_not_reinterpreted_as_s5_event():
    outputs = run(
        [
            {
                "source_id": "ca-1",
                "record_domain": "CORPORATE_ACTION",
                "available_at": "2024-05-31T12:00:00Z",
                "action_type": "split",
            }
        ]
    )
    assert outputs["clean_document_panel"]["records"] == []
    assert outputs["clean_event_reference_panel"]["records"] == []
    assert outputs["clean_context_source_panel"]["records"] == []
    assert outputs["clean_event_reference_panel"]["operational_domain_excluded_count"] == 1


def test_unknown_market_like_row_is_rejected_instead_of_becoming_context():
    outputs = run(
        [
            {
                "source_id": "market-1",
                "available_at": "2024-05-31T12:00:00Z",
                "close": 10.0,
            }
        ]
    )
    assert outputs["clean_context_source_panel"]["records"] == []
    assert outputs["clean_context_source_panel"]["unknown_domain_count"] == 1
    assert outputs["clean_context_source_panel"]["rejected_count"] == 1


def test_ids_are_deterministic_and_exact_duplicates_are_deduplicated():
    row = {
        "source_id": "s1",
        "record_domain": "DOCUMENT",
        "document_title": "Title",
        "document_text_or_path": "Body",
        "available_at": "2024-05-31T12:00:00Z",
    }
    first = run([row, dict(row)])
    second = run([row, dict(row)])

    first_document = first["clean_document_panel"]["records"][0]
    second_document = second["clean_document_panel"]["records"][0]
    assert first_document["document_id"] == second_document["document_id"]
    assert len(first["clean_document_panel"]["records"]) == 1
    assert first["clean_document_panel"]["duplicate_count"] == 1
    assert len(first["clean_event_reference_panel"]["records"]) == 1


def test_forbidden_fields_are_detected_recursively():
    with pytest.raises(Exception, match="forbidden output fields"):
        run(
            [
                {
                    "source_id": "s1",
                    "record_domain": "DOCUMENT",
                    "available_at": "2024-05-31T12:00:00Z",
                    "metadata": {"prediction": 0.9},
                }
            ]
        )


def test_missing_available_at_is_rejected_not_fabricated():
    with pytest.raises(Exception, match="available_at is required"):
        run([{"source_id": "s1", "record_domain": "DOCUMENT"}])
