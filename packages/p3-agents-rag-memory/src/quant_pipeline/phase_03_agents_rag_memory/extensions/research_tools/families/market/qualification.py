from __future__ import annotations

from collections.abc import Iterable

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .qualification_contracts import (
    HandlerBundleManifest,
    HandlerSpec,
    MarketDerivativesToolReadinessReport,
    OperationModeQualification,
    OperationModeQualificationPanel,
)
from .types import MarketMode, OptionMode, QualificationStatus
from .view_contracts import MarketViewBinding, OptionsViewBinding, ViewReadinessReport

_MARKET_VIEWS = {
    "get_snapshot": ("clean_underlying_panel",),
    "get_history": ("clean_underlying_panel",),
    "get_liquidity": ("clean_underlying_trade_panel",),
    "get_corporate_actions": ("clean_corporate_actions_panel",),
    "compare_instruments": ("clean_underlying_panel",),
}
_OPTIONS_VIEWS = {
    "get_contracts": ("clean_option_contract_panel",),
    "get_chain_snapshot": ("clean_option_contract_panel", "clean_option_quotes_panel"),
    "get_quote_history": ("clean_option_quotes_panel",),
    "get_surface_diagnostics": (
        "clean_option_contract_panel",
        "clean_option_quotes_panel",
        "clean_underlying_panel",
    ),
}


class MarketDerivativesQualificationBuilder:
    def market_observation_bundle(
        self,
        *,
        binding: MarketViewBinding,
        readiness: ViewReadinessReport,
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        specs = (
            self._spec(
                "market.observation.v1",
                "get_snapshot",
                "GetSnapshotRequest",
                (MarketMode.OBSERVE.value, MarketMode.DIAGNOSTIC.value),
            ),
            self._spec(
                "market.observation.v1",
                "get_history",
                "GetHistoryRequest",
                tuple(mode.value for mode in MarketMode),
            ),
            self._spec(
                "market.observation.v1",
                "get_liquidity",
                "GetLiquidityRequest",
                tuple(mode.value for mode in MarketMode),
            ),
        )
        return self._bundle_and_panel(
            snapshot_id=binding.snapshot_id,
            suffix="market_observation",
            specs=specs,
            readiness=readiness,
            view_map=_MARKET_VIEWS,
        )

    def market_structural_bundle(
        self,
        *,
        binding: MarketViewBinding,
        readiness: ViewReadinessReport,
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        specs = (
            self._spec(
                "market.observation.v1",
                "get_corporate_actions",
                "GetCorporateActionsRequest",
                tuple(mode.value for mode in MarketMode),
            ),
            self._spec(
                "market.observation.v1",
                "compare_instruments",
                "CompareInstrumentsRequest",
                tuple(mode.value for mode in MarketMode),
            ),
        )
        return self._bundle_and_panel(
            snapshot_id=binding.snapshot_id,
            suffix="market_structural",
            specs=specs,
            readiness=readiness,
            view_map=_MARKET_VIEWS,
        )

    def option_chain_bundle(
        self,
        *,
        binding: OptionsViewBinding,
        readiness: ViewReadinessReport,
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        specs = (
            self._spec(
                "options.observation.v1",
                "get_contracts",
                "GetContractsRequest",
                (OptionMode.CONTRACT_LOOKUP.value, OptionMode.CHAIN_DIAGNOSTIC.value),
            ),
            self._spec(
                "options.observation.v1",
                "get_chain_snapshot",
                "GetChainSnapshotRequest",
                (OptionMode.CONTRACT_LOOKUP.value, OptionMode.CHAIN_DIAGNOSTIC.value),
            ),
            self._spec(
                "options.observation.v1",
                "get_quote_history",
                "GetQuoteHistoryRequest",
                (OptionMode.CHAIN_DIAGNOSTIC.value, OptionMode.STRUCTURE_HISTORY.value),
            ),
        )
        return self._bundle_and_panel(
            snapshot_id=binding.snapshot_id,
            suffix="options_chain",
            specs=specs,
            readiness=readiness,
            view_map=_OPTIONS_VIEWS,
        )

    def option_surface_bundle(
        self,
        *,
        binding: OptionsViewBinding,
        readiness: ViewReadinessReport,
        sufficient_surface_coverage: bool,
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        specs = (
            self._spec(
                "options.observation.v1",
                "get_surface_diagnostics",
                "GetSurfaceDiagnosticsRequest",
                (
                    OptionMode.CHAIN_DIAGNOSTIC.value,
                    OptionMode.STRUCTURE_HISTORY.value,
                    OptionMode.SURFACE_ANALYSIS.value,
                ),
            ),
        )
        bundle, panel = self._bundle_and_panel(
            snapshot_id=binding.snapshot_id,
            suffix="options_surface",
            specs=specs,
            readiness=readiness,
            view_map=_OPTIONS_VIEWS,
        )
        records = []
        for record in panel.records:
            status = record.status
            reasons = list(record.reason_codes)
            if not binding.observed_iv_available:
                status = QualificationStatus.BLOCKED_UPSTREAM
                reasons.append("P3_RT_QUAL_OBSERVED_IV_UNAVAILABLE")
            elif not sufficient_surface_coverage:
                status = QualificationStatus.DEGRADED
                reasons.append("P3_RT_DATA_SURFACE_COVERAGE_LIMITED")
            records.append(record.model_copy(update={"status": status, "reason_codes": tuple(sorted(set(reasons))) }))
        return bundle, self._panel(binding.snapshot_id, tuple(records))

    def consolidate(
        self,
        *,
        snapshot_id: str,
        bundles: Iterable[HandlerBundleManifest],
        panels: Iterable[OperationModeQualificationPanel],
    ) -> tuple[
        HandlerBundleManifest,
        HandlerBundleManifest,
        OperationModeQualificationPanel,
        MarketDerivativesToolReadinessReport,
    ]:
        materialized_bundles = tuple(bundles)
        materialized_panels = tuple(panels)
        if any(panel.snapshot_id != snapshot_id for panel in materialized_panels):
            raise ValueError("market/options qualification panel snapshot_id mismatch")
        market_specs = tuple(
            sorted(
                (
                    item
                    for bundle in materialized_bundles
                    if bundle.tool_id == "market.observation.v1"
                    for item in bundle.handlers
                ),
                key=lambda item: item.operation_id,
            )
        )
        option_specs = tuple(
            sorted(
                (
                    item
                    for bundle in materialized_bundles
                    if bundle.tool_id == "options.observation.v1"
                    for item in bundle.handlers
                ),
                key=lambda item: item.operation_id,
            )
        )
        market_bundle = self._manifest(snapshot_id, "market_complete", "market.observation.v1", market_specs)
        option_bundle = self._manifest(snapshot_id, "options_complete", "options.observation.v1", option_specs)
        all_specs = (*market_specs, *option_specs)
        handler_keys = [(item.tool_id, item.operation_id) for item in all_specs]
        if len(handler_keys) != len(set(handler_keys)):
            raise ValueError("duplicate market/options handler operation")
        records = tuple(
            sorted(
                (record for panel in materialized_panels for record in panel.records),
                key=lambda item: (item.tool_id, item.operation_id, item.mode_id),
            )
        )
        qualification_keys = [(item.tool_id, item.operation_id, item.mode_id) for item in records]
        if len(qualification_keys) != len(set(qualification_keys)):
            raise ValueError("duplicate market/options operation/mode qualification")
        expected_keys = {
            (handler.tool_id, handler.operation_id, mode)
            for handler in all_specs
            for mode in handler.supported_modes
        }
        if set(qualification_keys) != expected_keys:
            raise ValueError("market/options handler and qualification coverage mismatch")
        panel = self._panel(snapshot_id, records)
        report = self._readiness_report(snapshot_id, records)
        return market_bundle, option_bundle, panel, report

    def _bundle_and_panel(
        self,
        *,
        snapshot_id: str,
        suffix: str,
        specs: tuple[HandlerSpec, ...],
        readiness: ViewReadinessReport,
        view_map: dict[str, tuple[str, ...]],
    ) -> tuple[HandlerBundleManifest, OperationModeQualificationPanel]:
        if binding_snapshot := getattr(readiness, "snapshot_id", None):
            if binding_snapshot != snapshot_id:
                raise ValueError("market/options binding and readiness snapshot_id mismatch")
        overlap = set(readiness.available_operations) & set(readiness.blocked_operations)
        if overlap:
            raise ValueError(f"operations cannot be both available and blocked: {sorted(overlap)}")
        records = tuple(
            self._qualification(spec, mode, readiness, view_map[spec.operation_id])
            for spec in specs
            for mode in spec.supported_modes
        )
        return (
            self._manifest(snapshot_id, suffix, specs[0].tool_id, specs),
            self._panel(snapshot_id, records),
        )

    @staticmethod
    def _qualification(
        spec: HandlerSpec,
        mode: str,
        readiness: ViewReadinessReport,
        required_views: tuple[str, ...],
    ) -> OperationModeQualification:
        qualified = spec.operation_id in readiness.available_operations
        status = QualificationStatus.QUALIFIED_LOCAL if qualified else QualificationStatus.BLOCKED_UPSTREAM
        reasons = () if qualified else ("P3_RT_DATA_VIEW_UNAVAILABLE",)
        return OperationModeQualification(
            tool_id=spec.tool_id,
            operation_id=spec.operation_id,
            mode_id=mode,
            status=status,
            reason_codes=reasons,
            required_views=required_views,
            test_targets=(
                "tests/unit/test_market_handlers.py" if spec.tool_id == "market.observation.v1" else "tests/unit/test_option_handlers.py",
                "tests/property/test_point_in_time_properties.py",
            ),
        )

    @staticmethod
    def _spec(
        tool_id: str,
        operation_id: str,
        request_model: str,
        modes: tuple[str, ...],
    ) -> HandlerSpec:
        return HandlerSpec(
            tool_id=tool_id,
            operation_id=operation_id,
            handler_id=f"p3.s36.{tool_id.split('.')[0]}.{operation_id}",
            request_model=request_model,
            supported_modes=modes,
        )

    @staticmethod
    def _manifest(
        snapshot_id: str,
        suffix: str,
        tool_id: str,
        specs: tuple[HandlerSpec, ...],
    ) -> HandlerBundleManifest:
        base = {
            "schema_id": f"{suffix}_handler_bundle.s36.v1",
            "bundle_id": f"{suffix}_{content_hash((snapshot_id, specs))[:20]}",
            "tool_id": tool_id,
            "handlers": specs,
        }
        return HandlerBundleManifest(content_hash=content_hash(base), **base)

    @staticmethod
    def _panel(
        snapshot_id: str,
        records: tuple[OperationModeQualification, ...],
    ) -> OperationModeQualificationPanel:
        base = {"snapshot_id": snapshot_id, "records": records}
        return OperationModeQualificationPanel(content_hash=content_hash(base), **base)

    @staticmethod
    def _readiness_report(
        snapshot_id: str,
        records: tuple[OperationModeQualification, ...],
    ) -> MarketDerivativesToolReadinessReport:
        failed = [record for record in records if record.status is QualificationStatus.FAILED]
        blocked = tuple(
            f"{record.tool_id}/{record.operation_id}:{record.mode_id}"
            for record in records
            if record.status is QualificationStatus.BLOCKED_UPSTREAM
        )
        available = tuple(
            sorted(
                {
                    f"{record.tool_id}/{record.operation_id}"
                    for record in records
                    if record.status in {QualificationStatus.QUALIFIED_LOCAL, QualificationStatus.DEGRADED}
                }
            )
        )
        if failed:
            status = QualificationStatus.FAILED
        elif blocked:
            status = QualificationStatus.DEGRADED
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        reasons = tuple(sorted({reason for record in records for reason in record.reason_codes}))
        base = {
            "snapshot_id": snapshot_id,
            "status": status,
            "available_tool_operations": available,
            "blocked_tool_operation_modes": blocked,
            "reason_codes": reasons,
        }
        return MarketDerivativesToolReadinessReport(content_hash=content_hash(base), **base)
