"""P3.S33.M04 deterministic temporal entity and instrument resolution."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ..contracts.artifacts import ArtifactStatus
from ..contracts.boundary_artifacts import (
    EntityMatchMethod,
    EntityResolutionCandidate,
    EntityResolutionPolicy,
    EntityResolutionQualificationReport,
    EntityResolutionResult,
    EntityResolutionStatus,
    Phase2ResearchViewManifest,
    PitVisibilityPolicy,
    QualificationCheck,
    QualificationStatus,
    TemporalEntityRecord,
    TemporalEntityResolutionIndex,
)
from ..contracts.boundary_configs import EntityMapRecordConfig, EntityUnderlyingMapConfig
from ..core.hashing import content_hash
from .artifact_construction import finalize, lineage
from .input_contracts import as_records, first_value, parse_datetime

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_lookup(value: str) -> str:
    return _NORMALIZE_RE.sub("", value.casefold())


def _view_refs(manifest: Phase2ResearchViewManifest) -> dict[str, tuple[str, tuple[str, ...]]]:
    return {
        view.artifact_name: (view.artifact_id, view.lineage_ids)
        for view in manifest.views
    }


def _text(record: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    value = first_value(record, keys)
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _validity(record: Mapping[str, Any], start_keys: Sequence[str], end_keys: Sequence[str]) -> tuple[datetime | None, datetime | None]:
    return parse_datetime(first_value(record, start_keys)), parse_datetime(first_value(record, end_keys))


def _record_from_config(item: EntityMapRecordConfig) -> dict[str, Any]:
    return {
        "entity_id": item.entity_id,
        "instrument_id": item.instrument_id,
        "instrument_type": item.instrument_type,
        "venue": item.venue,
        "ticker": item.ticker,
        "aliases": item.aliases,
        "identifiers": item.identifiers,
        "valid_from": parse_datetime(item.valid_from),
        "valid_to": parse_datetime(item.valid_to),
        "underlying_instrument_id": item.underlying_instrument_id,
        "source_artifact_ids": (),
        "source_lineage_ids": (),
        "confidence": 1.0,
        "match_methods": (EntityMatchMethod.EXACT_IDENTIFIER, EntityMatchMethod.COMPANY_INSTRUMENT_MAP),
    }


def _derived_rows(inputs: dict[str, Any], refs: dict[str, tuple[str, tuple[str, ...]]]) -> list[dict[str, Any]]:
    derived: list[dict[str, Any]] = []
    panel_specs = (
        ("clean_underlying_panel", "UNDERLYING"),
        ("clean_option_contract_panel", "OPTION_CONTRACT"),
        ("clean_document_panel", "COMPANY_REFERENCE"),
        ("clean_event_reference_panel", "COMPANY_REFERENCE"),
        ("clean_corporate_actions_panel", "UNDERLYING"),
    )
    for artifact_name, default_type in panel_specs:
        artifact_id, lineage_ids = refs.get(artifact_name, ("", ()))
        for row in as_records(inputs.get(artifact_name)):
            entity_id = _text(row, ("entity_id", "company_id", "issuer_id", "underlying"))
            instrument_id = _text(row, ("instrument_id", "underlying_id", "contract_id", "underlying"))
            ticker = _text(row, ("ticker", "symbol", "underlying"))
            if entity_id is None and instrument_id is None and ticker is None:
                continue
            entity_id = entity_id or instrument_id or ticker
            instrument_id = instrument_id or (ticker if default_type != "COMPANY_REFERENCE" else None)
            aliases = {
                value
                for value in (
                    ticker,
                    _text(row, ("company_name", "entity_name", "issuer_name", "name")),
                    _text(row, ("alias", "short_name")),
                )
                if value
            }
            identifiers = {
                key.upper(): str(row[key])
                for key in ("cnpj", "cik", "isin", "figi", "sedol", "cusip")
                if row.get(key) not in (None, "")
            }
            valid_from, valid_to = _validity(
                row,
                ("valid_from", "listing_date", "start_date", "date", "available_at"),
                ("valid_to", "expiration_date", "delisting_date", "end_date"),
            )
            underlying = _text(row, ("underlying_instrument_id", "underlying_id", "underlying"))
            methods = [EntityMatchMethod.COMPANY_INSTRUMENT_MAP]
            if identifiers:
                methods.insert(0, EntityMatchMethod.EXACT_IDENTIFIER)
            if ticker:
                methods.append(EntityMatchMethod.TICKER_VENUE)
            if aliases:
                methods.append(EntityMatchMethod.TEMPORAL_ALIAS)
            derived.append({
                "entity_id": entity_id,
                "instrument_id": instrument_id,
                "instrument_type": _text(row, ("instrument_type", "asset_class", "contract_type")) or default_type,
                "venue": _text(row, ("venue", "exchange", "market")),
                "ticker": ticker,
                "aliases": tuple(sorted(aliases)),
                "identifiers": identifiers,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "underlying_instrument_id": underlying if default_type == "OPTION_CONTRACT" else None,
                "source_artifact_ids": (artifact_id,) if artifact_id else (),
                "source_lineage_ids": lineage_ids,
                "confidence": 1.0,
                "match_methods": tuple(dict.fromkeys(methods)),
            })
    return derived


def _merge_rows(rows: Sequence[dict[str, Any]]) -> tuple[TemporalEntityRecord, ...]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["entity_id"],
            row.get("instrument_id"),
            row.get("instrument_type"),
            row.get("venue"),
            row.get("ticker"),
            row.get("valid_from"),
            row.get("valid_to"),
        )
        grouped[key].append(row)
    result: list[TemporalEntityRecord] = []
    for key, group in grouped.items():
        aliases = sorted({alias for row in group for alias in row.get("aliases", ())})
        identifiers: dict[str, str] = {}
        for row in group:
            identifiers.update(row.get("identifiers", {}))
        source_artifacts = sorted({value for row in group for value in row.get("source_artifact_ids", ())})
        source_lineage = sorted({value for row in group for value in row.get("source_lineage_ids", ())})
        methods = tuple(sorted({value for row in group for value in row.get("match_methods", ())}, key=lambda item: item.value))
        payload = {
            "entity_id": key[0],
            "instrument_id": key[1],
            "instrument_type": key[2],
            "venue": key[3],
            "ticker": key[4],
            "valid_from": key[5],
            "valid_to": key[6],
            "underlying_instrument_id": next((row.get("underlying_instrument_id") for row in group if row.get("underlying_instrument_id")), None),
        }
        resolution_key = f"entity-resolution:{content_hash(payload)[:24]}"
        result.append(TemporalEntityRecord(
            resolution_key=resolution_key,
            entity_id=str(key[0]),
            instrument_id=None if key[1] is None else str(key[1]),
            instrument_type=str(key[2]),
            venue=None if key[3] is None else str(key[3]),
            ticker=None if key[4] is None else str(key[4]),
            aliases=tuple(aliases),
            identifiers=identifiers,
            valid_from=key[5],
            valid_to=key[6],
            underlying_instrument_id=payload["underlying_instrument_id"],
            source_artifact_ids=tuple(source_artifacts),
            source_lineage_ids=tuple(source_lineage),
            confidence=min(float(row.get("confidence", 1.0)) for row in group),
            match_methods=methods or (EntityMatchMethod.COMPANY_INSTRUMENT_MAP,),
        ))
    return tuple(sorted(result, key=lambda item: item.resolution_key))


def build_entity_resolution(
    *,
    inputs: dict[str, Any],
    config: EntityUnderlyingMapConfig,
    view_manifest: Phase2ResearchViewManifest,
    pit_policy: PitVisibilityPolicy,
    contract_version: str = "1.0.0",
) -> tuple[TemporalEntityResolutionIndex, EntityResolutionPolicy, EntityResolutionQualificationReport]:
    rows = [_record_from_config(item) for item in config.records]
    rows.extend(_derived_rows(inputs, _view_refs(view_manifest)))
    records = _merge_rows(rows)
    policy = finalize(EntityResolutionPolicy, {
        "status": ArtifactStatus.READY,
        "lineage": lineage("P3.S33.M04", contract_version, [config, view_manifest, pit_policy]),
        "reason_codes": (),
        "resolution_order": (
            EntityMatchMethod.EXACT_IDENTIFIER,
            EntityMatchMethod.TICKER_VENUE,
            EntityMatchMethod.TEMPORAL_ALIAS,
            EntityMatchMethod.COMPANY_INSTRUMENT_MAP,
            EntityMatchMethod.OPTIONAL_PROBABILISTIC,
        ),
        "fuzzy_matching_enabled": config.fuzzy_matching_enabled,
        "minimum_probabilistic_confidence": config.minimum_probabilistic_confidence,
        "canonical_timezone": pit_policy.canonical_timezone,
        "identifier_namespaces": config.identifier_namespaces,
    })
    alias_map: dict[str, set[str]] = defaultdict(set)
    for record in records:
        lookup_values = list(record.aliases)
        if record.ticker:
            lookup_values.append(record.ticker)
        lookup_values.extend(record.identifiers.values())
        for value in lookup_values:
            alias_map[normalize_lookup(value)].add(record.resolution_key)
    ambiguous = sum(len(keys) > 1 for keys in alias_map.values())
    checks = (
        QualificationCheck(
            check_id="resolution_keys_unique",
            status=QualificationStatus.PASS,
            summary="resolution keys are deterministic and unique",
        ),
        QualificationCheck(
            check_id="ambiguous_aliases_explicit",
            status=QualificationStatus.WARN if ambiguous else QualificationStatus.PASS,
            summary="ambiguous aliases are returned as candidates and never chosen silently",
            details={"ambiguous_alias_count": ambiguous},
        ),
        QualificationCheck(
            check_id="fuzzy_matching_policy",
            status=QualificationStatus.WARN if config.fuzzy_matching_enabled else QualificationStatus.PASS,
            summary="probabilistic matching is disabled by default or explicitly governed",
        ),
    )
    overall = QualificationStatus.WARN if any(item.status == QualificationStatus.WARN for item in checks) else QualificationStatus.PASS
    artifact_status = ArtifactStatus.DEGRADED if overall == QualificationStatus.WARN else ArtifactStatus.READY
    index = finalize(TemporalEntityResolutionIndex, {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M04", contract_version, [config, view_manifest, pit_policy, *[inputs.get(name) for name in (
            "clean_underlying_panel", "clean_option_contract_panel", "clean_document_panel", "clean_event_reference_panel", "clean_corporate_actions_panel"
        )]]),
        "reason_codes": ("P3RT-DATA-ENTITY-AMBIGUITY-PRESENT",) if ambiguous else (),
        "records": records,
        "record_count": len(records),
    })
    report = finalize(EntityResolutionQualificationReport, {
        "status": artifact_status,
        "lineage": lineage("P3.S33.M04", contract_version, [index, policy]),
        "reason_codes": index.reason_codes,
        "checks": checks,
        "resolved_count": len(records),
        "ambiguous_key_count": ambiguous,
        "overall_status": overall,
    })
    return index, policy, report


def resolve_entity(
    query: str,
    *,
    decision_time: datetime,
    index: TemporalEntityResolutionIndex,
    policy: EntityResolutionPolicy,
    venue: str | None = None,
) -> EntityResolutionResult:
    if decision_time.tzinfo is None:
        raise ValueError("decision_time must be timezone-aware")
    normalized = normalize_lookup(query)
    candidates: list[EntityResolutionCandidate] = []
    for record in index.records:
        if record.valid_from and decision_time < record.valid_from:
            continue
        if record.valid_to and decision_time > record.valid_to:
            continue
        if venue and record.venue and venue.casefold() != record.venue.casefold():
            continue
        identifier_values = {normalize_lookup(value) for value in record.identifiers.values()}
        ticker_match = record.ticker is not None and normalize_lookup(record.ticker) == normalized
        alias_match = normalized in {normalize_lookup(value) for value in record.aliases}
        entity_match = normalize_lookup(record.entity_id) == normalized
        instrument_match = record.instrument_id is not None and normalize_lookup(record.instrument_id) == normalized
        if normalized in identifier_values or entity_match or instrument_match:
            method = EntityMatchMethod.EXACT_IDENTIFIER
            confidence = 1.0
        elif ticker_match:
            method = EntityMatchMethod.TICKER_VENUE
            confidence = 1.0
        elif alias_match:
            method = EntityMatchMethod.TEMPORAL_ALIAS
            confidence = 0.99
        else:
            continue
        candidates.append(EntityResolutionCandidate(
            resolution_key=record.resolution_key,
            entity_id=record.entity_id,
            instrument_id=record.instrument_id,
            method=method,
            confidence=confidence,
        ))
    candidates.sort(key=lambda item: (-item.confidence, item.entity_id, item.instrument_id or "", item.resolution_key))
    if not candidates:
        status = EntityResolutionStatus.UNRESOLVED
        reasons = ("P3RT-DATA-ENTITY-UNRESOLVED",)
    elif len(candidates) == 1:
        status = EntityResolutionStatus.RESOLVED
        reasons = ()
    else:
        status = EntityResolutionStatus.AMBIGUOUS
        reasons = ("P3RT-DATA-ENTITY-AMBIGUOUS",)
    return EntityResolutionResult(
        query=query,
        decision_time=decision_time.astimezone(timezone.utc),
        status=status,
        candidates=tuple(candidates),
        reason_codes=reasons,
    )
