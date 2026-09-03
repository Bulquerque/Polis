from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .normalization import artifact_identity, artifact_records
from .types import QualificationStatus, ViewReadinessStatus
from .view_contracts import BoundView, MarketViewBinding, OptionsViewBinding, ViewReadinessReport

_MARKET_REQUIREMENTS = {
    "get_snapshot": {
        "clean_underlying_panel": ("underlying", "date", "available_at", "close", "source_id", "lineage_id"),
    },
    "get_history": {
        "clean_underlying_panel": ("underlying", "date", "available_at", "close", "source_id", "lineage_id"),
    },
    "get_liquidity": {
        "clean_underlying_trade_panel": (
            "underlying",
            "date",
            "available_at",
            "volume",
            "financial_volume",
            "source_id",
            "lineage_id",
        ),
    },
    "get_corporate_actions": {
        "clean_corporate_actions_panel": (
            "underlying",
            "action_type",
            "available_at",
            "source_id",
            "lineage_id",
        ),
    },
    "compare_instruments": {
        "clean_underlying_panel": ("underlying", "date", "available_at", "close", "source_id", "lineage_id"),
    },
}

_OPTIONS_REQUIREMENTS = {
    "get_contracts": {
        "clean_option_contract_panel": (
            "contract_key",
            "option_id",
            "underlying",
            "option_type",
            "strike",
            "expiration_date",
            "first_seen_date",
            "source_id",
            "lineage_id",
        ),
    },
    "get_chain_snapshot": {
        "clean_option_contract_panel": (
            "contract_key",
            "underlying",
            "option_type",
            "strike",
            "expiration_date",
            "first_seen_date",
        ),
        "clean_option_quotes_panel": (
            "contract_key",
            "underlying",
            "option_type",
            "strike",
            "expiration_date",
            "date",
            "available_at",
            "source_id",
            "lineage_id",
        ),
    },
    "get_quote_history": {
        "clean_option_quotes_panel": (
            "contract_key",
            "date",
            "available_at",
            "source_id",
            "lineage_id",
        ),
    },
    "get_surface_diagnostics": {
        "clean_option_contract_panel": (
            "contract_key",
            "underlying",
            "option_type",
            "strike",
            "expiration_date",
            "first_seen_date",
        ),
        "clean_option_quotes_panel": (
            "contract_key",
            "underlying",
            "option_type",
            "strike",
            "expiration_date",
            "date",
            "available_at",
            "source_id",
            "lineage_id",
        ),
        "clean_underlying_panel": (
            "underlying",
            "date",
            "available_at",
            "close",
            "source_id",
            "lineage_id",
        ),
    },
}


class MarketViewBindingBuilder:
    def build(
        self,
        *,
        snapshot_id: str,
        artifacts: Mapping[str, object],
    ) -> tuple[MarketViewBinding, OptionsViewBinding, ViewReadinessReport, ViewReadinessReport]:
        names = sorted(set(_all_view_names()))
        views = {name: self._bind_view(name, artifacts.get(name)) for name in names}
        market = self._market_binding(snapshot_id, views)
        options = self._options_binding(snapshot_id, views)
        return (
            market,
            options,
            self._readiness(snapshot_id, "market", _MARKET_REQUIREMENTS, views),
            self._readiness(snapshot_id, "options", _OPTIONS_REQUIREMENTS, views),
        )

    @staticmethod
    def _bind_view(name: str, artifact: object) -> BoundView:
        if artifact is None:
            return BoundView(
                artifact_name=name,
                artifact_id=f"missing:{name}",
                schema_version="unknown",
                content_hash=content_hash(()),
                record_count=0,
                available_fields=(),
                status=ViewReadinessStatus.BLOCKED_UPSTREAM,
                reason_codes=("P3_RT_DATA_VIEW_UNAVAILABLE",),
            )
        records = artifact_records(artifact)
        artifact_id, schema_version, digest = artifact_identity(name, artifact)
        fields = tuple(sorted({key for row in records for key in row}))
        required = tuple(sorted(_required_fields_for_view(name)))
        missing = tuple(field for field in required if field not in fields)
        if missing:
            status = ViewReadinessStatus.DEGRADED
            reasons = ("P3_RT_DATA_REQUIRED_FIELD_MISSING",)
        elif not records:
            status = ViewReadinessStatus.DEGRADED
            reasons = ("P3_RT_DATA_EMPTY_VIEW",)
        else:
            status = ViewReadinessStatus.READY
            reasons = ()
        return BoundView(
            artifact_name=name,
            artifact_id=artifact_id,
            schema_version=schema_version,
            content_hash=digest,
            record_count=len(records),
            available_fields=fields,
            missing_required_fields=missing,
            status=status,
            reason_codes=reasons,
        )

    @staticmethod
    def _market_binding(snapshot_id: str, views: Mapping[str, BoundView]) -> MarketViewBinding:
        selected = tuple(views[name] for name in sorted({v for req in _MARKET_REQUIREMENTS.values() for v in req}))
        operation_map = {operation: tuple(requirements) for operation, requirements in _MARKET_REQUIREMENTS.items()}
        base = {"snapshot_id": snapshot_id, "views": selected, "operation_view_map": operation_map}
        return MarketViewBinding(content_hash=content_hash(base), **base)

    @staticmethod
    def _options_binding(snapshot_id: str, views: Mapping[str, BoundView]) -> OptionsViewBinding:
        selected = tuple(views[name] for name in sorted({v for req in _OPTIONS_REQUIREMENTS.values() for v in req}))
        operation_map = {operation: tuple(requirements) for operation, requirements in _OPTIONS_REQUIREMENTS.items()}
        quote_fields = set(views["clean_option_quotes_panel"].available_fields)
        observed_iv = bool({"iv", "implied_volatility"} & quote_fields)
        base = {
            "snapshot_id": snapshot_id,
            "views": selected,
            "operation_view_map": operation_map,
            "observed_iv_available": observed_iv,
        }
        return OptionsViewBinding(content_hash=content_hash(base), **base)

    @staticmethod
    def _readiness(
        snapshot_id: str,
        family: str,
        requirements: Mapping[str, Mapping[str, tuple[str, ...]]],
        views: Mapping[str, BoundView],
    ) -> ViewReadinessReport:
        available: list[str] = []
        blocked: list[str] = []
        reasons: set[str] = set()
        for operation, operation_requirements in requirements.items():
            operation_ready = True
            for view_name, fields in operation_requirements.items():
                view = views[view_name]
                if view.status is ViewReadinessStatus.BLOCKED_UPSTREAM:
                    operation_ready = False
                    reasons.update(view.reason_codes)
                    continue
                if any(field not in view.available_fields for field in fields):
                    operation_ready = False
                    reasons.add("P3_RT_DATA_REQUIRED_FIELD_MISSING")
            (available if operation_ready else blocked).append(operation)
        if not available:
            status = QualificationStatus.BLOCKED_UPSTREAM
        elif blocked:
            status = QualificationStatus.DEGRADED
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        base = {
            "schema_id": f"{family}_view_readiness_report.s36.v1",
            "snapshot_id": snapshot_id,
            "status": status,
            "available_operations": tuple(sorted(available)),
            "blocked_operations": tuple(sorted(blocked)),
            "reason_codes": tuple(sorted(reasons)),
        }
        return ViewReadinessReport(content_hash=content_hash(base), **base)


def _all_view_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                view
                for requirements in (*_MARKET_REQUIREMENTS.values(), *_OPTIONS_REQUIREMENTS.values())
                for view in requirements
            }
        )
    )


def _required_fields_for_view(view_name: str) -> set[str]:
    return {
        field
        for requirements in (*_MARKET_REQUIREMENTS.values(), *_OPTIONS_REQUIREMENTS.values())
        for name, fields in requirements.items()
        if name == view_name
        for field in fields
    }
