"""Explicit compact-V2 and V1 compatibility paths for P5."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from ..domain.enums import CapabilityStatus
from ..domain.models import MarketBeliefState, P5CompatibilityReport
from ..foundation.contracts import parse_external_records
from ..foundation.errors import Phase6ContractError
from ..foundation.hashing import canonical_sha256, stable_id, utc
from .p5_utils import as_datetime, horizon_days


def parse_compact_v2(
    artifact: Any,
    decision_time: datetime,
    module_id: str,
) -> tuple[MarketBeliefState, ...]:
    records = parse_external_records(
        artifact,
        MarketBeliefState,
        "market_belief_state",
        module_id,
    )
    for record in records:
        if record.decision_time != decision_time:
            raise Phase6ContractError(
                "belief decision time mismatch",
                "P6_MARKET_CLOCK_MISMATCH",
                module_id,
                {"belief_state_id": record.belief_state_id},
            )
    return records


def parse_v1(
    artifact: Any,
    decision_time: datetime,
    module_id: str,
) -> tuple[MarketBeliefState, ...]:
    if not isinstance(artifact, Mapping) or not isinstance(artifact.get("records"), list):
        raise Phase6ContractError(
            "V1 forecast artifact invalid",
            "P6_P5_MANIFEST_INVALID",
            module_id,
            {},
        )
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise Phase6ContractError(
            "V1 forecast artifact_id is required",
            "P6_P5_MANIFEST_INVALID",
            module_id,
            {},
        )
    return tuple(
        _adapt_v1_record(item, index, artifact_id, decision_time, module_id)
        for index, item in enumerate(artifact["records"])
    )


def _adapt_v1_record(
    item: Mapping[str, Any],
    index: int,
    artifact_id: str,
    decision_time: datetime,
    module_id: str,
) -> MarketBeliefState:
    underlying = item.get("underlying") or item.get("underlying_id")
    available_at = item.get("available_at") or item.get("prediction_timestamp") or item.get("as_of_time")
    horizon = item.get("horizon_days") if item.get("horizon_days") is not None else item.get("horizon")
    confidence = item.get("forecast_confidence")
    if confidence is None:
        confidence = item.get("confidence")
    if not underlying or available_at is None or horizon is None or confidence is None:
        raise Phase6ContractError(
            "V1 forecast missing required identity, clock, horizon, or confidence",
            "P6_P5_MANIFEST_INVALID",
            module_id,
            {"index": index},
        )
    if utc(as_datetime(available_at)) > decision_time:
        raise Phase6ContractError(
            "V1 forecast is future dated",
            "P6_P5_FORECAST_FUTURE_DATED",
            module_id,
            {"underlying_id": underlying},
        )
    days = int(horizon) if isinstance(horizon, int) else horizon_days(str(horizon))
    return MarketBeliefState(
        belief_state_id=stable_id("p5-v1", artifact_id, underlying, index),
        underlying_id=str(underlying),
        decision_time=decision_time,
        horizon_days=days,
        scenarios=(),
        confidence=Decimal(str(confidence)),
        regime_context="UNAVAILABLE",
        scenario_capability=CapabilityStatus.LIMITED,
        ambiguity_capability=CapabilityStatus.UNAVAILABLE,
        surface_capability=CapabilityStatus.UNAVAILABLE,
        source_artifact_id=artifact_id,
        source_record_id=str(item.get("record_id", index)),
        scenario_source="P5_V1_LIMITED",
        calibration_status="UNAVAILABLE",
        capability_reason_codes=("P5_V1_CAPABILITY_LIMITED",),
    )


def legacy_report(
    status: str,
    beliefs: tuple[MarketBeliefState, ...],
) -> P5CompatibilityReport:
    digest = canonical_sha256(tuple(row.model_dump(mode="json") for row in beliefs))
    return P5CompatibilityReport(
        manifest_id=f"legacy-{digest[:24]}",
        manifest_sha256=digest,
        upstream_run_id="LEGACY_UNAVAILABLE",
        upstream_cycle_id="LEGACY_UNAVAILABLE",
        upstream_lineage_id="LEGACY_UNAVAILABLE",
        p5_contract_version=status,
        validation_status="DEGRADED",
        full_manifest_consumed=False,
        receipts=(),
        scenario_sources={row.underlying_id: row.scenario_source for row in beliefs},
        artifact_usage={"legacy_input": status},
        reason_codes=(status,),
    )


def looks_like_native_p5(value: Any) -> bool:
    return isinstance(value, Mapping) and (
        value.get("producer_phase") == "P5" or value.get("artifact_sha256") is not None
    )
