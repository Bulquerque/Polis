from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import ValidationError

from ._compat import content_hash, validate_json
from .catalog_contracts import (
    AssetMacroContextDefinition,
    AssetMacroContextRegistrySnapshot,
    MacroSeriesReleaseCatalog,
    MacroViewReadinessReport,
)
from .normalization import (
    artifact_records,
    available_at,
    infer_frequency,
    normalize_region,
    numeric_value,
    observation_date,
    revision_id,
    row_sort_key,
    series_id,
    vintage_date,
)
from .result_contracts import MacroSeriesDefinition
from .types import Transformation, ViewReadinessStatus

_MACRO_VIEWS = ("clean_macro_br_panel", "clean_macro_us_panel")


class MacroSeriesReleaseCatalogBuilder:
    def build(
        self,
        *,
        snapshot_id: str,
        artifacts: Mapping[str, object],
        metadata_registry: object = None,
        asset_context_registry: object = None,
    ) -> tuple[
        MacroSeriesReleaseCatalog,
        MacroViewReadinessReport,
        AssetMacroContextRegistrySnapshot,
    ]:
        rows = tuple(
            row
            for view in _MACRO_VIEWS
            for row in artifact_records(artifacts.get(view))
        )
        metadata = self._metadata_index(metadata_registry)
        definitions = self._definitions(rows, metadata)
        contexts = self._context_records(asset_context_registry)
        catalog = self._catalog(snapshot_id, definitions)
        context_snapshot = self._context_snapshot(snapshot_id, contexts)
        readiness = self._readiness(snapshot_id, rows, definitions, contexts)
        return catalog, readiness, context_snapshot

    @staticmethod
    def _catalog(
        snapshot_id: str,
        definitions: tuple[MacroSeriesDefinition, ...],
    ) -> MacroSeriesReleaseCatalog:
        base = {"snapshot_id": snapshot_id, "records": definitions}
        return MacroSeriesReleaseCatalog(**base, content_hash=content_hash(base))

    @staticmethod
    def _context_snapshot(
        snapshot_id: str,
        contexts: tuple[AssetMacroContextDefinition, ...],
    ) -> AssetMacroContextRegistrySnapshot:
        base = {"snapshot_id": snapshot_id, "records": contexts}
        return AssetMacroContextRegistrySnapshot(
            **base,
            content_hash=content_hash(base),
        )

    @staticmethod
    def _metadata_index(value: object) -> dict[str, Mapping[str, object]]:
        return {
            str(row["series_id"]): row
            for row in artifact_records(value)
            if row.get("series_id") not in (None, "")
        }

    def _definitions(
        self,
        rows: tuple[dict[str, object], ...],
        metadata: Mapping[str, Mapping[str, object]],
    ) -> tuple[MacroSeriesDefinition, ...]:
        grouped = self._valid_rows_by_series(rows)
        return tuple(
            self._definition(sid, series_rows, metadata.get(sid, {}))
            for sid, series_rows in sorted(grouped.items())
        )

    @staticmethod
    def _valid_rows_by_series(
        rows: tuple[dict[str, object], ...],
    ) -> dict[str, list[dict[str, object]]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            sid = series_id(row)
            if sid is None or not MacroSeriesReleaseCatalogBuilder._valid_observation(row):
                continue
            grouped.setdefault(sid, []).append(row)
        for series_rows in grouped.values():
            series_rows.sort(key=row_sort_key)
        return grouped

    @staticmethod
    def _valid_observation(row: Mapping[str, object]) -> bool:
        try:
            observation_date(row)
            numeric_value(row)
            available_at(row)
        except (TypeError, ValueError):
            return False
        return True

    def _definition(
        self,
        sid: str,
        series_rows: list[dict[str, object]],
        metadata: Mapping[str, object],
    ) -> MacroSeriesDefinition:
        first = series_rows[0]
        region = normalize_region(
            metadata.get("region")
            or first.get("macro_region")
            or first.get("region")
            or first.get("country")
        )
        return MacroSeriesDefinition(
            series_id=sid,
            title=self._text(metadata.get("title") or first.get("title") or sid),
            aliases=tuple(str(item) for item in metadata.get("aliases") or ()),
            region=region,
            country=self._optional_text(metadata.get("country") or first.get("country") or region),
            family=self._optional_text(
                metadata.get("family")
                or first.get("family")
                or first.get("category")
            ),
            unit=self._optional_text(metadata.get("unit") or first.get("unit")),
            frequency=infer_frequency(metadata.get("frequency") or first.get("frequency")),
            seasonal_adjustment=self._optional_text(
                metadata.get("seasonal_adjustment") or first.get("seasonal_adjustment")
            ),
            source_id=self._text(metadata.get("source_id") or first.get("source_id") or "unknown"),
            release_id=self._optional_text(metadata.get("release_id") or first.get("release_id")),
            description=self._optional_text(metadata.get("description")),
            vintage_support=self._vintage_support(series_rows, metadata),
            allowed_transformations=self._transformations(first, metadata),
            valid_from=self._optional_date(metadata.get("valid_from"))
            or min(available_at(row).date() for row in series_rows),
            valid_to=self._optional_date(metadata.get("valid_to")),
        )

    @staticmethod
    def _transformations(
        first: Mapping[str, object],
        metadata: Mapping[str, object],
    ) -> tuple[Transformation, ...]:
        configured = (
            metadata.get("allowed_transformations")
            or first.get("allowed_transformations")
            or ("LEVEL",)
        )
        return tuple(Transformation(str(item)) for item in configured)

    @staticmethod
    def _vintage_support(
        rows: list[dict[str, object]],
        metadata: Mapping[str, object],
    ) -> bool:
        configured = metadata.get("vintage_support")
        if configured is not None:
            return MacroSeriesReleaseCatalogBuilder._configured_bool(configured)
        unique_dates = {observation_date(row) for row in rows}
        vintages = {
            (vintage_date(row), revision_id(row))
            for row in rows
            if vintage_date(row) is not None or revision_id(row) is not None
        }
        return len(unique_dates) < len(rows) and len(vintages) > 1

    @staticmethod
    def _configured_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"true", "1", "yes", "y"}

    @staticmethod
    def _context_records(value: object) -> tuple[AssetMacroContextDefinition, ...]:
        records: list[AssetMacroContextDefinition] = []
        for row in artifact_records(value):
            try:
                records.append(validate_json(AssetMacroContextDefinition, row))
            except (TypeError, ValueError, ValidationError):
                continue
        return tuple(sorted(records, key=lambda item: (item.asset_id, item.factor_id)))

    @staticmethod
    def _readiness(
        snapshot_id: str,
        rows: tuple[dict[str, object], ...],
        definitions: tuple[MacroSeriesDefinition, ...],
        contexts: tuple[AssetMacroContextDefinition, ...],
    ) -> MacroViewReadinessReport:
        available, blocked = MacroSeriesReleaseCatalogBuilder._operation_readiness(
            definitions,
            contexts,
        )
        vintage_count = sum(item.vintage_support for item in definitions)
        status = MacroSeriesReleaseCatalogBuilder._readiness_status(definitions, blocked)
        reasons = MacroSeriesReleaseCatalogBuilder._readiness_reasons(
            definitions,
            contexts,
            vintage_count,
        )
        base = {
            "snapshot_id": snapshot_id,
            "status": status,
            "available_operations": tuple(sorted(available)),
            "blocked_operations": tuple(sorted(blocked)),
            "available_fields": tuple(sorted({key for row in rows for key in row})),
            "series_count": len(definitions),
            "observation_count": len(rows),
            "vintage_capable_series_count": vintage_count,
            "reason_codes": tuple(sorted(reasons)),
        }
        return MacroViewReadinessReport(**base, content_hash=content_hash(base))

    @staticmethod
    def _operation_readiness(
        definitions: tuple[MacroSeriesDefinition, ...],
        contexts: tuple[AssetMacroContextDefinition, ...],
    ) -> tuple[list[str], list[str]]:
        checks = {
            "search_series": bool(definitions),
            "get_observations": bool(definitions),
            "get_release_snapshot": any(item.vintage_support for item in definitions),
            "compare_series": len(definitions) >= 2,
            "get_asset_context": bool(contexts),
        }
        available = [operation for operation, ready in checks.items() if ready]
        blocked = [operation for operation, ready in checks.items() if not ready]
        return available, blocked

    @staticmethod
    def _readiness_status(
        definitions: tuple[MacroSeriesDefinition, ...],
        blocked: list[str],
    ) -> ViewReadinessStatus:
        if not definitions:
            return ViewReadinessStatus.BLOCKED_UPSTREAM
        if blocked:
            return ViewReadinessStatus.DEGRADED
        return ViewReadinessStatus.READY

    @staticmethod
    def _readiness_reasons(
        definitions: tuple[MacroSeriesDefinition, ...],
        contexts: tuple[AssetMacroContextDefinition, ...],
        vintage_count: int,
    ) -> list[str]:
        reasons = []
        if not definitions:
            reasons.append("P3_RT_DATA_MACRO_SERIES_UNAVAILABLE")
        if vintage_count == 0:
            reasons.append("P3_RT_PIT_VINTAGE_UNAVAILABLE")
        if not contexts:
            reasons.append("P3_RT_DATA_ASSET_CONTEXT_REGISTRY_UNAVAILABLE")
        return reasons

    @staticmethod
    def _optional_date(value: object) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])

    @staticmethod
    def _optional_text(value: object) -> str | None:
        token = str(value or "").strip()
        return token or None

    @staticmethod
    def _text(value: object) -> str:
        return str(value).strip()
