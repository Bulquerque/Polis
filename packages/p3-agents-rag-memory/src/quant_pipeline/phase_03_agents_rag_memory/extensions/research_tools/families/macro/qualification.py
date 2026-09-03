from __future__ import annotations

from collections.abc import Iterable

from ._compat import content_hash
from .catalog_contracts import MacroViewReadinessReport
from .qualification_contracts import (
    HandlerBundleManifest,
    HandlerSpec,
    MacroToolReadinessReport,
    OperationModeQualification,
    OperationModeQualificationPanel,
)
from .types import MacroMode, QualificationStatus

_OPERATION_MODES = {
    "search_series": (MacroMode.LOOKUP.value, MacroMode.CONTEXT.value),
    "get_observations": (MacroMode.LOOKUP.value, MacroMode.CONTEXT.value, MacroMode.VINTAGE_ANALYSIS.value),
    "get_release_snapshot": (MacroMode.LOOKUP.value, MacroMode.VINTAGE_ANALYSIS.value),
    "compare_series": (MacroMode.CONTEXT.value, MacroMode.VINTAGE_ANALYSIS.value),
    "get_asset_context": (MacroMode.CONTEXT.value,),
}
_REQUEST_MODELS = {
    "search_series": "SearchSeriesRequest",
    "get_observations": "GetObservationsRequest",
    "get_release_snapshot": "GetReleaseSnapshotRequest",
    "compare_series": "CompareSeriesRequest",
    "get_asset_context": "GetAssetContextRequest",
}
_REQUIRED_VIEWS = {
    "search_series": ("clean_macro_br_panel", "clean_macro_us_panel"),
    "get_observations": ("clean_macro_br_panel", "clean_macro_us_panel"),
    "get_release_snapshot": ("clean_macro_br_panel", "clean_macro_us_panel"),
    "compare_series": ("clean_macro_br_panel", "clean_macro_us_panel"),
    "get_asset_context": ("asset_macro_context_registry",),
}


class MacroQualificationBuilder:
    def observation_bundle(
        self, *, snapshot_id: str, readiness: MacroViewReadinessReport
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        return self._bundle(
            snapshot_id=snapshot_id,
            suffix="macro_observation",
            operations=("search_series", "get_observations", "get_release_snapshot"),
            readiness=readiness,
        )

    def context_bundle(
        self, *, snapshot_id: str, readiness: MacroViewReadinessReport
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        return self._bundle(
            snapshot_id=snapshot_id,
            suffix="macro_context",
            operations=("compare_series", "get_asset_context"),
            readiness=readiness,
        )

    def consolidate(
        self,
        *,
        snapshot_id: str,
        bundles: Iterable[HandlerBundleManifest],
        panels: Iterable[OperationModeQualificationPanel],
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel, MacroToolReadinessReport]:
        bundle_items = tuple(bundles)
        panel_items = tuple(panels)
        if any(panel.snapshot_id != snapshot_id for panel in panel_items):
            raise ValueError("macro qualification panel snapshot_id mismatch")
        specs = tuple(
            sorted(
                (spec for bundle in bundle_items for spec in bundle.handlers),
                key=lambda item: item.operation_id,
            )
        )
        operation_ids = [item.operation_id for item in specs]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("duplicate macro handler operation_id")
        records = tuple(
            sorted(
                (record for panel in panel_items for record in panel.records),
                key=lambda item: (item.operation_id, item.mode_id),
            )
        )
        actual_keys = [(item.operation_id, item.mode_id) for item in records]
        if len(actual_keys) != len(set(actual_keys)):
            raise ValueError("duplicate macro operation/mode qualification")
        expected_keys = {
            (handler.operation_id, mode)
            for handler in specs
            for mode in handler.supported_modes
        }
        if set(actual_keys) != expected_keys:
            raise ValueError("macro handler and qualification coverage mismatch")
        manifest = self._manifest(snapshot_id, "macro_complete", specs)
        panel_base = {"snapshot_id": snapshot_id, "records": records}
        panel = OperationModeQualificationPanel(**panel_base, content_hash=content_hash(panel_base))
        report = self._readiness(snapshot_id, records)
        return manifest, panel, report

    def _bundle(
        self,
        *,
        snapshot_id: str,
        suffix: str,
        operations: tuple[str, ...],
        readiness: MacroViewReadinessReport,
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        specs = tuple(self._spec(operation) for operation in operations)
        records = tuple(
            self._qualification(operation, mode, readiness)
            for operation in operations
            for mode in _OPERATION_MODES[operation]
        )
        manifest = self._manifest(snapshot_id, suffix, specs)
        panel_base = {"snapshot_id": snapshot_id, "records": records}
        panel = OperationModeQualificationPanel(**panel_base, content_hash=content_hash(panel_base))
        return manifest, panel

    @staticmethod
    def _spec(operation: str) -> HandlerSpec:
        return HandlerSpec(
            tool_id="macro.observation.v1",
            operation_id=operation,
            handler_id=f"p3.s37.macro.{operation}",
            request_model=_REQUEST_MODELS[operation],
            supported_modes=_OPERATION_MODES[operation],
            required_views=_REQUIRED_VIEWS[operation],
        )

    @staticmethod
    def _qualification(
        operation: str,
        mode: str,
        readiness: MacroViewReadinessReport,
    ) -> OperationModeQualification:
        reasons = []
        available = operation in readiness.available_operations
        if not available:
            status = QualificationStatus.BLOCKED_UPSTREAM
            reasons.append("P3_RT_DATA_VIEW_UNAVAILABLE")
        elif mode == MacroMode.VINTAGE_ANALYSIS.value and readiness.vintage_capable_series_count == 0:
            status = QualificationStatus.BLOCKED_UPSTREAM
            reasons.append("P3_RT_PIT_VINTAGE_UNAVAILABLE")
        elif (
            mode == MacroMode.VINTAGE_ANALYSIS.value
            and readiness.vintage_capable_series_count < readiness.series_count
        ):
            status = QualificationStatus.DEGRADED
            reasons.append("P3_RT_PIT_VINTAGE_COVERAGE_PARTIAL")
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        return OperationModeQualification(
            tool_id="macro.observation.v1",
            operation_id=operation,
            mode_id=mode,
            status=status,
            reason_codes=tuple(reasons),
            required_views=_REQUIRED_VIEWS[operation],
            test_targets=(
                "tests/unit/test_handlers.py",
                "tests/property/test_point_in_time_properties.py",
            ),
        )

    @staticmethod
    def _manifest(snapshot_id: str, suffix: str, specs: tuple[HandlerSpec, ...]) -> HandlerBundleManifest:
        base = {
            "schema_id": f"{suffix}_handler_bundle.s37.v1",
            "bundle_id": f"{suffix}_{content_hash((snapshot_id, specs))[:20]}",
            "tool_id": "macro.observation.v1",
            "handlers": specs,
        }
        return HandlerBundleManifest(**base, content_hash=content_hash(base))

    @staticmethod
    def _readiness(
        snapshot_id: str,
        records: tuple[OperationModeQualification, ...],
    ) -> MacroToolReadinessReport:
        blocked = tuple(
            f"macro.observation.v1/{item.operation_id}:{item.mode_id}"
            for item in records if item.status is QualificationStatus.BLOCKED_UPSTREAM
        )
        available = tuple(
            sorted(
                {
                    f"macro.observation.v1/{item.operation_id}"
                    for item in records
                    if item.status
                    in {
                        QualificationStatus.QUALIFIED_LOCAL,
                        QualificationStatus.DEGRADED,
                    }
                }
            )
        )
        failed = any(item.status is QualificationStatus.FAILED for item in records)
        degraded = bool(blocked) or any(item.status is QualificationStatus.DEGRADED for item in records)
        if failed:
            status = QualificationStatus.FAILED
        elif degraded:
            status = QualificationStatus.DEGRADED
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        reasons = tuple(sorted({reason for item in records for reason in item.reason_codes}))
        base = {
            "snapshot_id": snapshot_id,
            "status": status,
            "available_tool_operations": available,
            "blocked_tool_operation_modes": blocked,
            "reason_codes": reasons,
        }
        return MacroToolReadinessReport(**base, content_hash=content_hash(base))
