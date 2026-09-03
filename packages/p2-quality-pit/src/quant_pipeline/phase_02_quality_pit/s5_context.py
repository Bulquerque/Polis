from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .modules._module_executor import ContractValidationError, _stable_digest
from .modules._p2_semantic_helpers import FORBIDDEN, available_at


DOCUMENT_TYPES = {
    "document",
    "news",
    "filing",
    "report",
    "transcript",
    "research",
    "social",
    "social_post",
}
EVENT_TYPES = {"event", "macro_event", "earnings_event", "corporate_announcement"}
CONTEXT_TYPES = {"context", "context_source", "source_context"}
OPERATIONAL_DOMAINS = {
    "macro",
    "benchmark",
    "calendar",
    "corporate_action",
    "underlying",
    "option_contract",
    "option_quote",
}


@dataclass(frozen=True)
class S5CleanResult:
    context_rows: list[dict]
    document_rows: list[dict]
    event_rows: list[dict]
    rejected_count: int
    unknown_domain_count: int
    operational_domain_excluded_count: int
    context_duplicate_count: int
    document_duplicate_count: int
    event_duplicate_count: int


def optional_records(value: Any, artifact_name: str) -> list[dict]:
    """Read an optional materialized artifact without fabricating missing rows."""
    if value in (None, {}):
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("records", "rows", "items", "sources"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return [dict(item) for item in candidate if isinstance(item, dict)]
        if value.get("source"):
            raise ContractValidationError(f"{artifact_name} cannot be synthesized from source")
        if value.get("artifact_id"):
            return []
    raise ContractValidationError(f"{artifact_name} must contain records")


def assert_no_forbidden_recursive(value: Any, path: str = "record") -> None:
    if isinstance(value, dict):
        leaked = sorted(set(value).intersection(FORBIDDEN))
        if leaked:
            raise ContractValidationError(
                f"forbidden output fields detected at {path}: {leaked}"
            )
        for key, item in value.items():
            assert_no_forbidden_recursive(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_forbidden_recursive(item, f"{path}[{index}]")


def stable_id(prefix: str, payload: dict) -> str:
    return f"{prefix}-{_stable_digest(payload)[:20]}"


def build_quality_index(panel: Any) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for row in optional_records(panel, "source_quality_panel"):
        source_id = row.get("source_id")
        if not source_id:
            continue
        key = str(source_id)
        previous = index.get(key)
        if previous is None or (
            previous.get("quality_score") is None and row.get("quality_score") is not None
        ):
            index[key] = row
    return index


def classify_domain(row: dict) -> str:
    explicit = row.get("record_domain") or row.get("domain")
    if explicit:
        value = str(explicit).strip().lower()
        aliases = {
            "context_source": "context",
            "source_context": "context",
            "news": "document",
            "filing": "document",
            "report": "document",
            "transcript": "document",
            "research": "document",
            "social": "document",
            "social_post": "document",
            "macro_event": "event",
            "earnings_event": "event",
            "corporate_announcement": "event",
        }
        return aliases.get(value, value)

    legacy_type = str(
        row.get("document_type") or row.get("record_type") or row.get("event_type") or ""
    ).strip().lower()
    if legacy_type in DOCUMENT_TYPES:
        return "document"
    if legacy_type in EVENT_TYPES:
        return "event"
    if legacy_type in CONTEXT_TYPES:
        return "context"
    if legacy_type == "corporate_action":
        return "corporate_action"

    context_markers = ("source_name", "source_type", "context_type")
    market_markers = (
        "open",
        "high",
        "low",
        "close",
        "strike",
        "expiration_date",
        "benchmark_id",
        "series_id",
        "adjustment_factor",
    )
    has_context = any(row.get(key) not in (None, "") for key in context_markers)
    has_market_data = any(row.get(key) not in (None, "") for key in market_markers)
    return "context" if has_context and not has_market_data else "unknown"


def clean_s5_records(input_rows: list[dict], source_quality_panel: Any) -> S5CleanResult:
    quality_index = build_quality_index(source_quality_panel)
    context_rows: list[dict] = []
    document_rows: list[dict] = []
    event_rows: list[dict] = []
    rejected_count = 0
    unknown_domain_count = 0
    operational_domain_count = 0

    for raw_row in input_rows:
        row = dict(raw_row)
        assert_no_forbidden_recursive(row)
        domain = classify_domain(row)

        if domain in OPERATIONAL_DOMAINS:
            operational_domain_count += 1
            continue
        if domain == "unknown":
            unknown_domain_count += 1
            rejected_count += 1
            continue

        if domain == "context":
            context_rows.append(_clean_context(row, quality_index))
        elif domain == "document":
            document = _clean_document(row, quality_index)
            document_rows.append(document)
            context_rows.append(
                _clean_context(row, quality_index, derived_from="document_source")
            )
            # Compatibility-safe: publication is a factual event, explicitly marked as derived.
            event_rows.append(_document_publication_event(document))
        elif domain == "event":
            event_rows.append(_clean_event(row, quality_index))
            context_rows.append(
                _clean_context(row, quality_index, derived_from="event_source")
            )

    context_rows, context_duplicates = _dedupe_context(context_rows)
    document_rows, document_duplicates = _dedupe(document_rows, "document_id")
    event_rows, event_duplicates = _dedupe(event_rows, "event_id")

    return S5CleanResult(
        context_rows=context_rows,
        document_rows=document_rows,
        event_rows=event_rows,
        rejected_count=rejected_count,
        unknown_domain_count=unknown_domain_count,
        operational_domain_excluded_count=operational_domain_count,
        context_duplicate_count=context_duplicates,
        document_duplicate_count=document_duplicates,
        event_duplicate_count=event_duplicates,
    )


def _source_id(row: dict, entity: str) -> str:
    source_id = str(row.get("source_id") or "").strip()
    if not source_id:
        raise ContractValidationError(f"source_id is required for S5 {entity}")
    return source_id


def _lineage_id(row: dict, source_id: str) -> str:
    if row.get("lineage_id"):
        return str(row["lineage_id"])
    return stable_id("lineage-context", {"source_id": source_id, "row": row})


def _quality(row: dict, quality_index: dict[str, dict]) -> tuple[float, str, dict]:
    source_id = str(row["source_id"])
    source_quality = quality_index.get(source_id)
    if source_quality is not None:
        raw_score = source_quality.get("quality_score")
        try:
            score = float(raw_score) if raw_score is not None else 0.0
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                f"invalid quality_score for source_id={source_id}"
            ) from exc
        return score, "known", source_quality

    if row.get("source_quality_score") is not None:
        try:
            return float(row["source_quality_score"]), "row_fallback", {}
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                f"invalid source_quality_score for source_id={source_id}"
            ) from exc

    return 0.0, "unknown", {}


def _reference_date(row: dict, avail: str) -> str:
    for key in ("reference_date", "published_at", "event_date", "date"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)[:10]
    return str(avail)[:10]


def _copy_pit_metadata(source: dict, target: dict) -> None:
    """Keep temporal provenance intact across the S5 cleaning boundary."""
    for key in (
        "pit_status",
        "pit_granularity",
        "availability_basis",
        "available_date",
        "revision_id",
        "vintage_date",
        "realtime_start",
        "realtime_end",
        "decision_time",
    ):
        if source.get(key) not in (None, ""):
            target[key] = source[key]


def _clean_context(
    row: dict,
    quality_index: dict[str, dict],
    *,
    derived_from: str | None = None,
) -> dict:
    source_id = _source_id(row, "context records")
    avail = available_at(row)
    score, quality_status, source_quality = _quality(
        {**row, "source_id": source_id}, quality_index
    )
    result = {
        "source_id": source_id,
        "source_name": str(
            row.get("source_name") or source_quality.get("source_name") or source_id
        ),
        "source_type": str(
            row.get("source_type") or source_quality.get("source_type") or "unknown"
        ),
        "available_at": avail,
        "quality_score": score,
        "quality_status": quality_status,
        "readability_status": source_quality.get("readability_status", "unknown"),
        "error_flag": bool(source_quality.get("error_flag", False)),
        "warning_flag": bool(
            source_quality.get("warning_flag", quality_status != "known")
        ),
        "lineage_id": _lineage_id(row, source_id),
    }
    _copy_pit_metadata(row, result)
    for key in ("provider", "language", "region"):
        if row.get(key) not in (None, ""):
            result[key] = row[key]
    if derived_from:
        result["context_origin"] = derived_from
    assert_no_forbidden_recursive(result)
    return result


def _clean_document(row: dict, quality_index: dict[str, dict]) -> dict:
    source_id = _source_id(row, "documents")
    normalized = {**row, "source_id": source_id}
    avail = available_at(normalized)
    score, quality_status, source_quality = _quality(normalized, quality_index)

    content = (
        row.get("document_text_or_path")
        or row.get("text")
        or row.get("content")
        or row.get("path")
        or row.get("uri")
        or ""
    )
    document_id = row.get("document_id") or row.get("provider_document_id")
    if not document_id:
        document_id = stable_id(
            "doc",
            {
                "source_id": source_id,
                "available_at": avail,
                "reference_date": row.get("reference_date"),
                "path": row.get("path") or row.get("uri"),
                "content": content,
            },
        )

    ingested_at = row.get("ingested_at") or row.get("retrieved_at")
    ingested_inferred = ingested_at in (None, "")
    if ingested_inferred:
        ingested_at = avail

    document_type = str(
        row.get("document_type") or row.get("record_type") or "document"
    ).lower()
    if document_type not in DOCUMENT_TYPES:
        document_type = "document"

    result = {
        "document_id": str(document_id),
        "source_id": source_id,
        "source_name": str(
            row.get("source_name") or source_quality.get("source_name") or source_id
        ),
        "document_type": document_type,
        "document_title": str(row.get("document_title") or row.get("title") or ""),
        "document_text_or_path": str(content),
        "reference_date": _reference_date(row, avail),
        "available_at": avail,
        "ingested_at": str(ingested_at),
        "source_quality_score": score,
        "source_quality_status": quality_status,
        "language": str(row.get("language") or "und"),
        "cleaning_status": "clean" if content else "degraded",
        "lineage_id": _lineage_id(row, source_id),
    }
    _copy_pit_metadata(row, result)
    if ingested_inferred:
        result["ingested_at_status"] = "inferred_from_available_at"
    if row.get("provider_document_id"):
        result["provider_document_id"] = str(row["provider_document_id"])
    if row.get("content_mode"):
        result["content_mode"] = str(row["content_mode"])
    elif row.get("path") or row.get("uri"):
        result["content_mode"] = "ARTIFACT_PATH"
    elif content:
        result["content_mode"] = "INLINE_TEXT"
    else:
        result["content_mode"] = "MISSING"
    assert_no_forbidden_recursive(result)
    return result


def _clean_event(row: dict, quality_index: dict[str, dict]) -> dict:
    source_id = _source_id(row, "events")
    normalized = {**row, "source_id": source_id}
    avail = available_at(normalized)
    score, quality_status, _ = _quality(normalized, quality_index)
    event_type = str(row.get("event_type") or row.get("record_type") or "event").lower()
    event_id = row.get("event_id") or row.get("provider_event_id")
    if not event_id:
        event_id = stable_id(
            "event",
            {
                "source_id": source_id,
                "event_type": event_type,
                "reference_date": _reference_date(row, avail),
                "available_at": avail,
                "underlying": row.get("underlying"),
                "document_id": row.get("document_id"),
            },
        )

    result = {
        "event_id": str(event_id),
        "event_type": event_type,
        "source_id": source_id,
        "reference_date": _reference_date(row, avail),
        "available_at": avail,
        "source_quality_score": score,
        "source_quality_status": quality_status,
        "lineage_id": _lineage_id(row, source_id),
    }
    _copy_pit_metadata(row, result)
    for key in ("document_id", "underlying", "entity_id", "event_status", "provider_event_id"):
        if row.get(key) not in (None, ""):
            result[key] = row[key]
    assert_no_forbidden_recursive(result)
    return result


def _document_publication_event(document: dict) -> dict:
    result = {
        "event_id": stable_id(
            "event-docpub",
            {
                "document_id": document["document_id"],
                "available_at": document["available_at"],
            },
        ),
        "event_type": "document_publication",
        "source_id": document["source_id"],
        "document_id": document["document_id"],
        "reference_date": document["reference_date"],
        "available_at": document["available_at"],
        "source_quality_score": document["source_quality_score"],
        "source_quality_status": document["source_quality_status"],
        "event_origin": "derived_document_publication",
        "lineage_id": document["lineage_id"],
    }
    _copy_pit_metadata(document, result)
    assert_no_forbidden_recursive(result)
    return result


def _dedupe(rows: list[dict], key: str) -> tuple[list[dict], int]:
    unique: list[dict] = []
    seen: set[str] = set()
    duplicates = 0
    for row in rows:
        value = row.get(key)
        if value in (None, ""):
            raise ContractValidationError(f"{key} is required for deterministic deduplication")
        token = str(value)
        if token in seen:
            duplicates += 1
            continue
        seen.add(token)
        unique.append(row)
    return unique, duplicates


def _dedupe_context(rows: list[dict]) -> tuple[list[dict], int]:
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    duplicates = 0
    for row in rows:
        token = (str(row["source_id"]), str(row["available_at"]))
        if token in seen:
            duplicates += 1
            continue
        seen.add(token)
        unique.append(row)
    return unique, duplicates
