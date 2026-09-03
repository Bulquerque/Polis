"""Shared primitives for P2.S1 admission, raw materialization, and source quality.

This module is intentionally small and provider-neutral. P2.S1 never performs
network calls; it validates and materializes snapshots already captured by P1.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from ._module_executor import ContractValidationError

_SHA256_HEX_LENGTH = 64
_SUPPORTED_FORMATS = {"csv", "json", "jsonl", "parquet"}
_B3_FORMAT = "b3_cotahist"
_RESERVED_PROVENANCE_FIELDS = (
    "source_id",
    "raw_artifact_id",
    "raw_artifact_path",
    "file_hash",
    "ingestion_run_id",
    "lineage_id",
    "declared_available_at",
    "source_reference_date",
    "ingested_at",
    "readability_status",
)


def rows_or_empty(value: Any, artifact: str) -> list[dict]:
    """Return materialized rows while accepting an empty legacy artifact envelope."""
    if value in (None, {}):
        return []
    if isinstance(value, dict):
        for key in ("records", "rows", "items", "sources", "snapshots", "checks", "hints", "errors", "tasks"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [dict(item) for item in rows if isinstance(item, dict)]
        if value.get("source"):
            raise ContractValidationError(f"{artifact} cannot be synthesized from source")
        # A valid envelope can legitimately contain no row collection.
        if {"artifact_id", "created_at", "lineage_id", "pipeline_version"}.intersection(value):
            return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    raise ContractValidationError(f"{artifact} must contain records or an explicit empty artifact envelope")


def match_rows(reference: dict, candidates: list[dict]) -> list[dict]:
    """Match related records using the strongest shared identifiers available."""
    raw_artifact_id = reference.get("raw_artifact_id")
    if raw_artifact_id:
        exact = [row for row in candidates if row.get("raw_artifact_id") == raw_artifact_id]
        if exact:
            return exact

    handoff_artifact_id = reference.get("handoff_artifact_id")
    if handoff_artifact_id:
        exact = [row for row in candidates if row.get("handoff_artifact_id") == handoff_artifact_id]
        if exact:
            return exact

    source_id = reference.get("source_id")
    if source_id:
        exact = [row for row in candidates if row.get("source_id") == source_id]
        if exact:
            return exact
    return []


def compare_shared_fields(
    reference: dict,
    candidate: dict,
    fields: Iterable[str],
    *,
    error_prefix: str,
) -> list[dict]:
    """Compare only fields present on both sides, preserving legacy-minimal schemas."""
    findings: list[dict] = []
    for field in fields:
        left = reference.get(field)
        right = candidate.get(field)
        if left in (None, "") or right in (None, ""):
            continue
        if str(left) != str(right):
            findings.append(
                {
                    "code": f"{error_prefix}_{field.upper()}_MISMATCH",
                    "severity": "BLOCK",
                    "field": field,
                    "expected": left,
                    "observed": right,
                }
            )
    return findings


def is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != _SHA256_HEX_LENGTH:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_artifact_path(raw_path: str, config: dict) -> Path:
    """Resolve a P1 raw path while optionally enforcing explicit allowed roots."""
    candidate = Path(raw_path).expanduser()
    artifact_root = config.get("artifact_root")
    if not candidate.is_absolute() and artifact_root:
        candidate = Path(artifact_root).expanduser() / candidate
    candidate = candidate.resolve()

    allowed_roots = config.get("allowed_roots") or []
    if allowed_roots:
        resolved_roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        if not any(candidate == root or root in candidate.parents for root in resolved_roots):
            raise ContractValidationError(
                f"P2_S1_M02_PATH_OUTSIDE_ROOT: {candidate} is outside configured allowed_roots"
            )
    return candidate


def detect_format(path: Path, descriptor: dict) -> str:
    declared = descriptor.get("format") or descriptor.get("file_format")
    if declared:
        normalized = str(declared).strip().lower().lstrip(".")
        if normalized in {"ndjson", "jsonlines"}:
            normalized = "jsonl"
        if normalized in _SUPPORTED_FORMATS:
            return normalized
        if normalized in {"b3", "cotahist", "b3_cotahist"}:
            return _B3_FORMAT

    content_type = str(descriptor.get("content_type") or "").lower()
    content_type_map = {
        "text/csv": "csv",
        "application/json": "json",
        "application/x-ndjson": "jsonl",
        "application/vnd.apache.parquet": "parquet",
    }
    if content_type in content_type_map:
        return content_type_map[content_type]

    source_category = str(descriptor.get("source_category") or descriptor.get("domain") or "").strip().lower()
    dataset = str(descriptor.get("dataset") or descriptor.get("dataset_id") or "").strip().lower()
    if source_category in {"b3", "bovespa"} and (dataset in {"cotahist", "cotahist_daily", "cotahist_annual"} or "cotahist" in dataset):
        return _B3_FORMAT

    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"ndjson", "jsonlines"}:
        suffix = "jsonl"
    if suffix in _SUPPORTED_FORMATS:
        return suffix
    raise ContractValidationError(f"P2_S1_M02_UNSUPPORTED_FORMAT: cannot determine format for {path}")


def _b3_date(value: str, *, field: str) -> str | None:
    token = value.strip()
    if not token or token == "0" * len(token):
        return None
    try:
        return datetime.strptime(token, "%Y%m%d").date().isoformat()
    except ValueError as exc:
        raise ContractValidationError(f"P2_S1_M02_B3_INVALID_{field.upper()}: {value!r}") from exc


def _b3_decimal(value: str, *, scale: int, field: str) -> float | None:
    token = value.strip()
    if not token or token == "0" * len(token):
        return None
    try:
        return float(Decimal(token) / (Decimal(10) ** scale))
    except (InvalidOperation, ValueError) as exc:
        raise ContractValidationError(f"P2_S1_M02_B3_INVALID_{field.upper()}: {value!r}") from exc


def _b3_integer(value: str, *, field: str) -> int | None:
    token = value.strip()
    if not token or token == "0" * len(token):
        return None
    try:
        return int(token)
    except ValueError as exc:
        raise ContractValidationError(f"P2_S1_M02_B3_INVALID_{field.upper()}: {value!r}") from exc


def read_b3_cotahist(path: Path, config: dict, payload: bytes | None = None) -> list[dict]:
    """Read the fixed-width B3 COTAHIST layout without changing raw bytes.

    The public B3 layout defines 245-byte records: 00 header, 01 quote and 99
    trailer. Header/trailer are custody metadata; only quote records enter the
    normalized row stream. ``strict_b3_layout`` defaults to true so an unknown
    binary file can never be mistaken for market data.
    """
    payload = path.read_bytes() if payload is None else payload
    if len(payload) % 245 == 0:
        lines = [payload[index : index + 245] for index in range(0, len(payload), 245)]
    else:
        lines = payload.splitlines()
    if not lines:
        raise ContractValidationError(f"P2_S1_M02_B3_EMPTY_FILE: {path}")
    rows: list[dict] = []
    saw_header = False
    saw_trailer = False
    declared_total: int | None = None
    for line_number, raw_line in enumerate(lines, start=1):
        text = raw_line.decode("latin-1")
        if len(text) != 245:
            raise ContractValidationError(
                f"P2_S1_M02_B3_RECORD_LENGTH: line={line_number} expected=245 observed={len(text)}"
            )
        record_type = text[0:2]
        if record_type == "00":
            saw_header = True
            continue
        if record_type == "99":
            saw_trailer = True
            declared_total = _b3_integer(text[31:42], field="total_records")
            continue
        if record_type != "01":
            raise ContractValidationError(
                f"P2_S1_M02_B3_UNKNOWN_RECORD_TYPE: line={line_number} type={record_type!r}"
            )

        trade_date = _b3_date(text[2:10], field="trade_date")
        if trade_date is None:
            raise ContractValidationError(f"P2_S1_M02_B3_TRADE_DATE_MISSING: line={line_number}")
        market_type = text[24:27].strip() or None
        option_market = market_type in {"070", "080"}
        row = {
            "record_domain": "OPTION_QUOTE" if option_market else "UNDERLYING" if market_type not in {"012", "013"} else "UNKNOWN",
            "record_type": "01",
            "source_category": "b3",
            "dataset": "cotahist",
            "asset_class": "OPTION" if option_market else "EQUITY",
            "exchange": "B3",
            "market": "B3",
            "date": trade_date,
            "reference_date": trade_date,
            "observation_date": trade_date,
            "bdi_code": text[10:12].strip() or None,
            "symbol": text[12:24].strip() or None,
            "underlying": text[12:24].strip() or None,
            "market_type": market_type,
            "company_name": text[27:39].strip() or None,
            "security_specification": text[39:49].strip() or None,
            "currency": text[52:56].strip() or None,
            "open": _b3_decimal(text[56:69], scale=2, field="open"),
            "high": _b3_decimal(text[69:82], scale=2, field="high"),
            "low": _b3_decimal(text[82:95], scale=2, field="low"),
            "average_price": _b3_decimal(text[95:108], scale=2, field="average_price"),
            "close": _b3_decimal(text[108:121], scale=2, field="close"),
            "bid": _b3_decimal(text[121:134], scale=2, field="bid"),
            "ask": _b3_decimal(text[134:147], scale=2, field="ask"),
            "trade_count": _b3_integer(text[147:152], field="trade_count"),
            "quantity": _b3_integer(text[152:170], field="quantity"),
            "volume": _b3_decimal(text[170:188], scale=2, field="volume"),
            "exercise_price": _b3_decimal(text[188:201], scale=2, field="exercise_price"),
            "expiration_date": _b3_date(text[202:210], field="expiration_date"),
            "quotation_factor": _b3_integer(text[210:217], field="quotation_factor"),
            "isin": text[230:242].strip() or None,
            "source_record_number": line_number,
        }
        if option_market:
            row.update({
                "option_id": row["symbol"],
                "option_type": "CALL" if market_type == "070" else "PUT",
                "strike": row["exercise_price"],
                "symbol": None,
                "underlying": None,
            })
            mapping = config.get("option_underlying_map") or {}
            mapped = mapping.get(str(row["option_id"]))
            if isinstance(mapped, (list, tuple, set)):
                if len(mapped) != 1:
                    raise ContractValidationError(
                        f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_AMBIGUOUS: {row['option_id']}"
                    )
                mapped = next(iter(mapped))
            registry = config.get("option_underlying_registry") or {}
            expected = registry.get(str(row["option_id"]))
            if expected is not None and str(mapped) != str(expected):
                raise ContractValidationError(
                    f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_MISMATCH: {row['option_id']}"
                )
            validity = (config.get("option_underlying_validity") or {}).get(str(row["option_id"]))
            if mapped is not None and validity:
                trade_date = row.get("trade_date") or row.get("date") or row.get("reference_date")
                if not trade_date:
                    raise ContractValidationError(
                        f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_DATE_MISSING: {row['option_id']}"
                    )
                if validity.get("valid_from") and trade_date < str(validity["valid_from"]):
                    raise ContractValidationError(
                        f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_NOT_YET_VALID: {row['option_id']}"
                    )
                if validity.get("valid_until") and trade_date > str(validity["valid_until"]):
                    raise ContractValidationError(
                        f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_EXPIRED: {row['option_id']}"
                    )
            if mapped is not None:
                row["underlying"] = str(mapped)
            elif config.get("strict_option_underlying_mapping"):
                raise ContractValidationError(
                    f"P2_S1_M02_OPTION_UNDERLYING_MAPPING_MISSING: {row['option_id']}"
                )
        rows.append(row)

    if not saw_header or not saw_trailer:
        raise ContractValidationError("P2_S1_M02_B3_HEADER_TRAILER_REQUIRED")
    if declared_total is not None and declared_total != len(lines):
        raise ContractValidationError(
            f"P2_S1_M02_B3_RECORD_COUNT_MISMATCH: declared={declared_total} observed={len(lines)}"
        )
    return rows


def _decode_option_payload(payload: Any, descriptor: dict) -> list[dict]:
    provider = str(descriptor.get("provider") or descriptor.get("source_id") or "").lower()
    captured_at = (
        descriptor.get("retrieved_at")
        or descriptor.get("ingested_at")
        or descriptor.get("declared_available_at")
    )

    def document_row(
        *, document_id: str, title: str, body: str | None, reference_date: str | None,
        available_at: Any = None, document_type: str = "document", source_url: str | None = None,
    ) -> dict[str, Any]:
        observed = available_at or captured_at
        return {
            "record_domain": "DOCUMENT",
            "document_id": document_id,
            "source_id": descriptor.get("source_id") or provider,
            "source_name": descriptor.get("source_name") or provider,
            "source_type": descriptor.get("source_type") or "api",
            "document_type": document_type,
            "document_title": title or document_id,
            "document_text_or_path": body or source_url or title or document_id,
            "reference_date": str(reference_date or observed or "")[:10],
            "available_at": observed,
            "ingested_at": descriptor.get("ingested_at") or observed,
            "language": "en",
            "lineage_id": descriptor.get("lineage_id"),
            "source_url": source_url,
        }

    if provider == "alpha_vantage_news" and isinstance(payload, dict):
        feed = payload.get("feed")
        if isinstance(feed, list):
            output = []
            for index, item in enumerate(feed, start=1):
                if not isinstance(item, dict):
                    continue
                published = str(item.get("time_published") or "")
                published_at = (
                    f"{published[:4]}-{published[4:6]}-{published[6:8]}T"
                    f"{published[9:11]}:{published[11:13]}:{published[13:15]}Z"
                    if len(published) >= 15 and published[8] == "T" else captured_at
                )
                output.append(document_row(
                    document_id=str(item.get("url") or f"{provider}-{index}"),
                    title=str(item.get("title") or ""),
                    body=item.get("summary"),
                    reference_date=published_at,
                    available_at=published_at,
                    document_type="news",
                    source_url=item.get("url"),
                ))
            return output

    if provider == "gdelt" and isinstance(payload, dict):
        articles = payload.get("articles") or payload.get("data") or []
        output = []
        for index, item in enumerate(articles, start=1):
            if not isinstance(item, dict) or not (item.get("url") or item.get("title")):
                continue
            seen = str(item.get("seendate") or "")
            available = (
                f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}T{seen[9:11]}:{seen[11:13]}:{seen[13:15]}Z"
                if len(seen) >= 15 and seen[8] == "T"
                else captured_at
            )
            document = document_row(
                document_id=str(item.get("url") or f"{provider}-{index}"),
                title=str(item.get("title") or ""),
                body=None,
                reference_date=available,
                available_at=available,
                document_type="news",
                source_url=item.get("url"),
            )
            document["source_name"] = str(item.get("domain") or document["source_name"])
            document["language"] = str(item.get("language") or "und")
            output.append(document)
        return output

    if provider == "sec" and isinstance(payload, dict):
        recent = ((payload.get("filings") or {}).get("recent") or {})
        if isinstance(recent, dict):
            output = []
            forms = recent.get("form") or []
            accession_numbers = recent.get("accessionNumber") or []
            filing_dates = recent.get("filingDate") or []
            report_dates = recent.get("reportDate") or []
            primary_documents = recent.get("primaryDocument") or []
            cik = str(payload.get("cik") or "").lstrip("0")
            for index, form in enumerate(forms):
                accession = str(accession_numbers[index]) if index < len(accession_numbers) else f"sec-{index}"
                filing_date = filing_dates[index] if index < len(filing_dates) else None
                report_date = report_dates[index] if index < len(report_dates) else filing_date
                primary = primary_documents[index] if index < len(primary_documents) else None
                accession_path = accession.replace("-", "")
                source_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{primary}"
                    if cik and primary else None
                )
                output.append(document_row(
                    document_id=f"sec:{accession}",
                    title=f"SEC filing {form}",
                    body=source_url,
                    reference_date=report_date or filing_date,
                    available_at=(f"{filing_date}T00:00:00Z" if filing_date else captured_at),
                    document_type="filing",
                    source_url=source_url,
                ))
            return output

    if provider == "lse" and isinstance(payload, dict) and (payload.get("underlying_candles") or payload.get("option_candles")):
        output = []
        for row in payload.get("underlying_candles", []):
            if not isinstance(row, dict) or row.get("close") is None:
                continue
            observed = row.get("timestamp") or descriptor.get("available_at")
            output.append({"record_domain": "UNDERLYING", "benchmark_id": row.get("symbol") or descriptor.get("underlying") or "AAPL", "date": str(observed)[:10], "close": row.get("close"), "volume": row.get("volume"), "available_at": observed, "observed_at": observed})
        for row in payload.get("option_candles", []):
            if not isinstance(row, dict) or not row.get("ticker"):
                continue
            observed = row.get("minute") or descriptor.get("available_at")
            output.append({"record_domain": "OPTION_QUOTE", "option_id": row.get("ticker"), "underlying": row.get("underlying"), "expiration_date": row.get("expiry"), "option_type": row.get("contract_type"), "strike": row.get("strike"), "last_price": row.get("close"), "volume": row.get("volume"), "implied_volatility": row.get("iv_avg"), "delta": row.get("delta_avg"), "gamma": row.get("gamma_avg"), "theta": row.get("theta_avg"), "vega": row.get("vega_avg"), "available_at": observed, "observed_at": observed})
        return output
    if provider == "lse" and isinstance(payload, list):
        return [{"record_domain": "OPTION_QUOTE", "option_id": row.get("ticker"), "underlying": row.get("underlying"), "expiration_date": row.get("expiry"), "option_type": row.get("contract_type"), "strike": row.get("strike"), "last_price": row.get("last_price"), "volume": row.get("volume_today"), "open_interest": row.get("open_interest"), "implied_volatility": row.get("iv"), "delta": row.get("delta"), "gamma": row.get("gamma"), "theta": row.get("theta"), "vega": row.get("vega"), "available_at": row.get("updated_at") or descriptor.get("available_at"), "observed_at": row.get("last_trade_at") or row.get("updated_at") or descriptor.get("available_at")} for row in payload if isinstance(row, dict) and row.get("ticker")]
    raw_rows = payload.get("data") if isinstance(payload, dict) else None
    if provider in {"fred", "alfred"} and isinstance(payload, dict):
        observations = payload.get("observations") or payload.get("data") or []
        source_family = "ALFRED_VINTAGE" if provider == "alfred" or any(
            isinstance(row, dict) and (row.get("realtime_start") or row.get("vintage_date"))
            for row in observations
        ) else "FRED_STATIC_EXPORT"
        output = []
        for index, row in enumerate(observations, start=1):
            if not isinstance(row, dict):
                continue
            available = row.get("available_at") or row.get("realtime_start") or descriptor.get("available_at")
            vintage = row.get("vintage_date") or row.get("realtime_start")
            output.append({
                "record_domain": "MACRO",
                "provider": provider.upper(),
                "source_family": source_family,
                "vintage_semantics": "VINTAGE_SAFE" if source_family == "ALFRED_VINTAGE" else "LATEST_REVISED_VALUE",
                "strict_historical_pit_eligible": source_family == "ALFRED_VINTAGE",
                "availability_status": "KNOWN" if available else "UNKNOWN_FROM_SOURCE",
                "series_id": descriptor.get("series_id") or payload.get("id") or payload.get("series_id"),
                "reference_date": row.get("date") or row.get("observation_date"),
                "vintage_date": vintage,
                "value": row.get("value"),
                "available_at": available,
                "source_row_number": index,
                "lineage_id": descriptor.get("lineage_id"),
            })
        return output
    if provider == "alpha_vantage" and isinstance(raw_rows, list):
        return [{"record_domain": "OPTION_QUOTE", "option_id": row.get("contractID"), "underlying": descriptor.get("underlying") or row.get("symbol"), "expiration_date": row.get("expiration"), "option_type": row.get("type"), "strike": row.get("strike"), "bid": row.get("bid"), "ask": row.get("ask"), "last_price": row.get("last"), "volume": row.get("volume"), "open_interest": row.get("open_interest"), "available_at": row.get("timestamp") or descriptor.get("available_at"), "observed_at": row.get("timestamp") or descriptor.get("available_at")} for row in raw_rows if isinstance(row, dict) and row.get("contractID")]
    if provider == "alpaca" and isinstance(payload, dict):
        output = []
        for bar in payload.get("underlying_bars", []):
            if not isinstance(bar, dict) or bar.get("c") is None or bar.get("t") is None:
                continue
            observed = bar.get("t")
            output.append({"record_domain": "UNDERLYING", "benchmark_id": "AAPL", "underlying": "AAPL", "date": str(observed)[:10], "close": bar.get("c"), "open": bar.get("o"), "high": bar.get("h"), "low": bar.get("l"), "volume": bar.get("v"), "available_at": observed, "observed_at": observed})
        for contract, row in payload.get("snapshots", payload).items():
            if not isinstance(row, dict):
                continue
            match = re.match(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$", str(contract))
            if not match:
                continue
            root, expiry, right, strike = match.groups()
            quote = row.get("latestQuote") or {}
            output.append({"record_domain": "OPTION_QUOTE", "option_id": contract, "underlying": root, "expiration_date": f"20{expiry[:2]}-{expiry[2:4]}-{expiry[4:6]}", "option_type": "CALL" if right == "C" else "PUT", "strike": int(strike) / 1000, "bid": quote.get("bp"), "ask": quote.get("ap"), "volume": (row.get("latestTrade") or {}).get("s"), "open_interest": None, "available_at": quote.get("t") or descriptor.get("available_at"), "observed_at": quote.get("t") or descriptor.get("available_at")})
        return output
    if provider == "bea" and isinstance(payload, dict):
        results = (payload.get("BEAAPI") or {}).get("Results") or {}
        output = []
        for index, row in enumerate(results.get("Data", []), start=1):
            if not isinstance(row, dict):
                continue
            raw_value = row.get("DataValue")
            try:
                numeric = float(str(raw_value).replace(",", "")) if raw_value not in (None, "") else None
            except (TypeError, ValueError):
                numeric = None
            captured_at = descriptor.get("retrieved_at") or descriptor.get("ingested_at") or descriptor.get("declared_available_at")
            output.append({"record_domain": "MACRO", "provider": "BEA", "region": "US", "series_id": row.get("SeriesCode"), "frequency": "Q", "reference_period": row.get("TimePeriod"), "capture_id": descriptor.get("capture_id"), "raw_record_id": f"bea-row-{index}", "source_row_number": index, "dataset_name": row.get("TableName") or "NIPA", "table_name": row.get("TableName"), "line_number": row.get("LineNumber"), "line_description": row.get("LineDescription"), "observation_period": row.get("TimePeriod"), "time_period": row.get("TimePeriod"), "data_value_raw": raw_value, "data_value_numeric": numeric, "observation_value": numeric, "unit": row.get("CL_UNIT"), "unit_multiplier": row.get("UNIT_MULT"), "note_ref": row.get("NoteRef"), "captured_at": captured_at, "available_at": captured_at, "release_at": None, "vintage_id": None, "availability_temporal_status": "UNKNOWN_RELEASE_TIME", "pit_ready": False})
        return output
    if provider == "eia" and isinstance(payload, dict):
        response = payload.get("response") or {}
        output = []
        captured_at = descriptor.get("retrieved_at") or descriptor.get("ingested_at") or descriptor.get("declared_available_at")
        for index, row in enumerate(response.get("data", []), start=1):
            if not isinstance(row, dict):
                continue
            raw_value = row.get("value")
            try:
                numeric = float(str(raw_value).replace(",", "")) if raw_value not in (None, "") else None
            except (TypeError, ValueError):
                numeric = None
            output.append({"record_domain": "MACRO", "provider": "EIA", "region": "US", "series_id": row.get("seriesId") or row.get("respondent"), "frequency": "HOURLY", "reference_period": row.get("period"), "capture_id": descriptor.get("capture_id"), "raw_record_id": f"eia-row-{index}", "source_row_number": index, "observation_period": row.get("period"), "data_value_raw": raw_value, "data_value_numeric": numeric, "observation_value": numeric, "unit": row.get("value-units"), "unit_multiplier": None, "captured_at": captured_at, "available_at": captured_at, "release_at": None, "vintage_id": None, "availability_temporal_status": "UNKNOWN_RELEASE_TIME", "pit_ready": False})
        return output
    return []


def read_artifact_rows(path: Path, format_name: str, config: dict, descriptor: dict | None = None) -> list[dict]:
    try:
        if format_name == "csv":
            encoding = str(config.get("csv_encoding") or "utf-8")
            delimiter = str(config.get("csv_delimiter") or ",")
            with path.open("r", encoding=encoding, newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]

        if format_name == "json":
            with path.open("r", encoding=str(config.get("json_encoding") or "utf-8")) as handle:
                payload = json.load(handle)
            decoded = _decode_option_payload(payload, descriptor or {})
            if decoded:
                return decoded
            if isinstance(payload, list):
                return [dict(row) for row in payload if isinstance(row, dict)]
            if isinstance(payload, dict):
                for key in ("records", "rows", "items", "data"):
                    if isinstance(payload.get(key), list):
                        return [dict(row) for row in payload[key] if isinstance(row, dict)]
                return [dict(payload)]
            raise ContractValidationError(f"P2_S1_M02_READ_FAILURE: JSON root must be object or array: {path}")

        if format_name == "jsonl":
            output: list[dict] = []
            encoding = str(config.get("json_encoding") or "utf-8")
            with path.open("r", encoding=encoding) as handle:
                for line_number, line in enumerate(handle, start=1):
                    text = line.strip()
                    if not text:
                        continue
                    payload = json.loads(text)
                    if not isinstance(payload, dict):
                        raise ContractValidationError(
                            f"P2_S1_M02_READ_FAILURE: JSONL line {line_number} must be an object"
                        )
                    output.append(dict(payload))
            return output

        if format_name == "parquet":
            try:
                import pandas as pd
            except Exception as exc:  # pragma: no cover - dependency/environment guard
                raise ContractValidationError("P2_S1_M02_PARQUET_DEPENDENCY_MISSING: pandas is required") from exc
            try:
                frame = pd.read_parquet(path)
            except ImportError as exc:
                raise ContractValidationError(
                    "P2_S1_M02_PARQUET_DEPENDENCY_MISSING: install pyarrow or fastparquet"
                ) from exc
            return frame.to_dict(orient="records")

        if format_name == _B3_FORMAT:
            if path.suffix.lower() == ".zip":
                max_members = int(config.get("max_zip_members", 1))
                max_expanded = int(config.get("max_zip_expanded_bytes", 512 * 1024 * 1024))
                with zipfile.ZipFile(path) as archive:
                    members = [m for m in archive.infolist() if not m.is_dir()]
                    if len(members) == 0 or len(members) > max_members:
                        raise ContractValidationError(
                            f"P2_S1_M02_B3_ZIP_MEMBER_COUNT: expected 1..{max_members}, observed={len(members)}"
                        )
                    member = members[0]
                    if member.file_size > max_expanded:
                        raise ContractValidationError(
                            f"P2_S1_M02_B3_ZIP_EXPANDED_SIZE: {member.file_size} > {max_expanded}"
                        )
                    if Path(member.filename).name != member.filename:
                        raise ContractValidationError("P2_S1_M02_B3_ZIP_SLIP_MEMBER")
                    member_payload = archive.read(member)
                return read_b3_cotahist(path, config, member_payload)
            return read_b3_cotahist(path, config)

        raise ContractValidationError(f"P2_S1_M02_UNSUPPORTED_FORMAT: {format_name}")
    except ContractValidationError:
        raise
    except Exception as exc:
        raise ContractValidationError(f"P2_S1_M02_READ_FAILURE: cannot read {path}: {exc}") from exc


def enrich_with_provenance(
    row: dict,
    descriptor: dict,
    row_number: int,
    *,
    physical_hash: str | None,
    hash_verified: bool,
) -> dict:
    output = dict(row)
    provenance: dict[str, Any] = {
        "raw_row_number": row_number,
        "physical_hash_verified": bool(hash_verified),
    }
    for field in _RESERVED_PROVENANCE_FIELDS:
        canonical_value = descriptor.get(field)
        if canonical_value not in (None, ""):
            provenance[field] = canonical_value
            output.setdefault(field, canonical_value)
    if physical_hash:
        provenance["physical_file_hash"] = physical_hash
    output["_provenance"] = provenance
    return output


def group_by_source(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        source_id = row.get("source_id")
        if source_id:
            grouped[str(source_id)].append(row)
    return dict(grouped)
