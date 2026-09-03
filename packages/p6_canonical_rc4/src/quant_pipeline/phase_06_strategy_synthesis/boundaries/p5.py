"""Public P5 compatibility boundary for P6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..domain.models import MarketBeliefState, P5CompatibilityReport
from ..foundation.errors import Phase6ContractError
from .p5_legacy import (
    legacy_report,
    looks_like_native_p5,
    parse_compact_v2,
    parse_v1,
)
from .p5_manifest import validate_full_p5_bundle
from .p5_scenarios import adapt_full_bundle


@dataclass(frozen=True, slots=True)
class ParsedP5Handoff:
    beliefs: tuple[MarketBeliefState, ...]
    report: P5CompatibilityReport


def parse_p5_handoff(
    inputs: dict[str, Any],
    decision_time: datetime,
    module_id: str,
    *,
    max_distribution_scenarios: int = 101,
    allow_unmanifested_legacy: bool = True,
    expected_run_id: str | None = None,
    expected_cycle_id: str | None = None,
) -> ParsedP5Handoff:
    """Validate and adapt a native full V2 bundle or explicit legacy path."""
    if "phase6_strategy_scenario_manifest" in inputs:
        bundle = validate_full_p5_bundle(
            inputs, decision_time, module_id,
            expected_run_id=expected_run_id, expected_cycle_id=expected_cycle_id,
        )
        beliefs, sources, reasons = adapt_full_bundle(
            bundle,
            inputs,
            decision_time,
            module_id,
            max_distribution_scenarios=max_distribution_scenarios,
        )
        report = P5CompatibilityReport(
            manifest_id=bundle.manifest.artifact_id,
            manifest_sha256=bundle.manifest.artifact_sha256,
            upstream_run_id=bundle.manifest.run_id,
            upstream_cycle_id=bundle.manifest.cycle_id,
            upstream_lineage_id=bundle.manifest.lineage_id,
            p5_contract_version=bundle.manifest.contract_version_for_receipt,
            validation_status=(
                "COMPLETE_LEGACY_REPLAY"
                if bundle.manifest.is_legacy_descriptor
                else "COMPLETE_CANONICAL"
            ),
            full_manifest_consumed=True,
            receipts=bundle.receipts,
            scenario_sources=sources,
            artifact_usage=_artifact_usage(sources, bundle),
            reason_codes=tuple(sorted(set(reasons))),
        )
        return ParsedP5Handoff(beliefs, report)
    if looks_like_native_p5(inputs.get("market_belief_state")):
        raise Phase6ContractError(
            "native P5 V2 artifact requires phase6_strategy_scenario_manifest",
            "P6_P5_MANIFEST_INVALID",
            module_id,
            {},
        )
    if ("market_belief_state" in inputs or "underlying_forecast_panel" in inputs) and not allow_unmanifested_legacy:
        raise Phase6ContractError(
            "unmanifested legacy P5 handoff is disabled for canonical runs",
            "P6_P5_LEGACY_DOWNGRADE_FORBIDDEN",
            module_id,
            {"explicit_opt_in_required": True},
        )
    if "market_belief_state" in inputs:
        beliefs = parse_compact_v2(inputs["market_belief_state"], decision_time, module_id)
        return ParsedP5Handoff(beliefs, legacy_report("COMPACT_V2_WITHOUT_MANIFEST", beliefs))
    if "underlying_forecast_panel" in inputs:
        beliefs = parse_v1(inputs["underlying_forecast_panel"], decision_time, module_id)
        return ParsedP5Handoff(beliefs, legacy_report("V1_LIMITED_ADAPTER", beliefs))
    raise Phase6ContractError(
        "P5 belief input is required",
        "P6_P5_MANIFEST_INVALID",
        module_id,
        {},
    )


def parse_p5_beliefs(
    inputs: dict[str, Any],
    decision_time: datetime,
    module_id: str,
) -> tuple[MarketBeliefState, ...]:
    """Backward-compatible record-only API."""
    return parse_p5_handoff(inputs, decision_time, module_id).beliefs


def _artifact_usage(sources, bundle) -> dict[str, str]:
    selected = set(sources.values())
    return {
        "market_belief_state": "SEMANTICALLY_CONSUMED",
        "return_distributions": (
            "SCENARIO_SOURCE_CONSUMED"
            if "P5_RETURN_DISTRIBUTION" in selected
            else "INTEGRITY_VALIDATED_NOT_SELECTED"
        ),
        "volatility_distributions": "INTEGRITY_VALIDATED_RESERVED_FOR_VALUATION",
        "path_risk_forecasts": "INTEGRITY_VALIDATED_RESERVED_FOR_PATH_RISK",
        "scenario_paths": (
            "SCENARIO_SOURCE_CONSUMED"
            if "P5_SCENARIO_PATHS" in selected
            else "INTEGRITY_VALIDATED_NOT_SELECTED"
        ),
        "ambiguity_sets": (
            "SEMANTICALLY_CONSUMED_METADATA_DISTRIBUTIONS_UNRESOLVED"
            if bundle.ambiguity_sets
            else "INTEGRITY_VALIDATED_UNAVAILABLE"
        ),
        "dependence_states": "INTEGRITY_VALIDATED_RESERVED_FOR_MULTI_UNDERLYING",
        "regime_ood_states": "SEMANTICALLY_CONSUMED",
        "forecast_confidence": "SEMANTICALLY_CONSUMED",
        "availability_report": "INTEGRITY_VALIDATED",
        "lineage_report": "INTEGRITY_VALIDATED",
    }
