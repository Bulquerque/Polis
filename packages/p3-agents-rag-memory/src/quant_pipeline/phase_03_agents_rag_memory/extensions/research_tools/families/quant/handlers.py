"""Explicit quantitative handler bindings and process-local factory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .dependence_handlers import CorrelationHandler, EntropyHandler
from .event_handlers import EventWindowHandler, ScenarioShockHandler
from .model_base import ExtensionLineage, QuantMode
from .models import HandlerBindingSpec, HandlerBundleManifest, hashed_payload
from .ports import PitResearchQueryPort
from .return_handlers import DrawdownHandler, RealizedVolatilityHandler, ReturnStatisticsHandler

RETURN_RISK_BINDINGS = (
    HandlerBindingSpec(
        operation_id="return_statistics",
        handler_id="quant.return_statistics.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/return_statistics_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("market_prices",),
    ),
    HandlerBindingSpec(
        operation_id="realized_volatility",
        handler_id="quant.realized_volatility.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/realized_volatility_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("market_prices",),
    ),
    HandlerBindingSpec(
        operation_id="drawdown",
        handler_id="quant.drawdown.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/drawdown_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("market_prices",),
    ),
)

DEPENDENCE_ENTROPY_BINDINGS = (
    HandlerBindingSpec(
        operation_id="correlation",
        handler_id="quant.correlation.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/correlation_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("market_prices",),
    ),
    HandlerBindingSpec(
        operation_id="entropy",
        handler_id="quant.entropy.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/entropy_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("market_prices",),
    ),
)

EVENT_SCENARIO_BINDINGS = (
    HandlerBindingSpec(
        operation_id="event_window",
        handler_id="quant.event_window.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/event_window_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=("events", "market_prices"),
    ),
    HandlerBindingSpec(
        operation_id="scenario_shock",
        handler_id="quant.scenario_shock.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/quant/scenario_shock_request.schema.json",
        result_schema_ref="extensions/research_tools/schemas/quant/quant_operation_result.schema.json",
        supported_modes=(QuantMode.BASIC, QuantMode.ROBUST, QuantMode.STABILITY),
        required_view_ids=(),
    ),
)


def build_handler_bundle(
    *,
    bundle_id: str,
    handlers: tuple[HandlerBindingSpec, ...],
    lineage: ExtensionLineage,
) -> HandlerBundleManifest:
    payload = {
        "bundle_id": bundle_id,
        "bundle_version": "1.0.0",
        "handlers": handlers,
        "lineage": lineage,
    }
    return HandlerBundleManifest(**payload, bundle_hash=hashed_payload(payload))


def build_return_risk_bundle(lineage: ExtensionLineage) -> HandlerBundleManifest:
    return build_handler_bundle(
        bundle_id="quant.return_risk_volatility.handlers.v1",
        handlers=RETURN_RISK_BINDINGS,
        lineage=lineage,
    )


def build_dependence_entropy_bundle(lineage: ExtensionLineage) -> HandlerBundleManifest:
    return build_handler_bundle(
        bundle_id="quant.dependence_entropy.handlers.v1",
        handlers=DEPENDENCE_ENTROPY_BINDINGS,
        lineage=lineage,
    )


def build_event_scenario_bundle(lineage: ExtensionLineage) -> HandlerBundleManifest:
    return build_handler_bundle(
        bundle_id="quant.event_scenario.handlers.v1",
        handlers=EVENT_SCENARIO_BINDINGS,
        lineage=lineage,
    )


@dataclass(frozen=True, slots=True)
class QuantHandlerFactory:
    query_port: PitResearchQueryPort

    def build(self) -> dict[str, Any]:
        return {
            "return_statistics": ReturnStatisticsHandler(self.query_port),
            "realized_volatility": RealizedVolatilityHandler(self.query_port),
            "drawdown": DrawdownHandler(self.query_port),
            "correlation": CorrelationHandler(self.query_port),
            "entropy": EntropyHandler(self.query_port),
            "event_window": EventWindowHandler(self.query_port),
            "scenario_shock": ScenarioShockHandler(),
        }
