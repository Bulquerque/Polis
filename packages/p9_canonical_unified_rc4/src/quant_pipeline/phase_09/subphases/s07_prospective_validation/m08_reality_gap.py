"""P9.S7.M08 — simulation, shadow, and live reality-gap evaluation."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from statistics import fmean

from pydantic import Field, field_validator, model_validator

from .canonical import payload_sha256
from .contracts import EvidenceClass, NonEmptyStr, StrictModel


class ExecutionStage(StrEnum):
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE = "LIVE"


class TransportabilityState(StrEnum):
    TRANSPORTABLE = "TRANSPORTABLE"
    TRANSPORTABLE_WITH_LIMITATIONS = "TRANSPORTABLE_WITH_LIMITATIONS"
    SIMULATION_BIAS_DETECTED = "SIMULATION_BIAS_DETECTED"
    EXECUTION_MODEL_MISSPECIFIED = "EXECUTION_MODEL_MISSPECIFIED"
    SHADOW_EVIDENCE_INSUFFICIENT = "SHADOW_EVIDENCE_INSUFFICIENT"
    NOT_TRANSPORTABLE = "NOT_TRANSPORTABLE"


class StageExecutionRecord(StrictModel):
    decision_id: NonEmptyStr
    cohort_id: NonEmptyStr
    policy_id: NonEmptyStr
    instrument_id: NonEmptyStr
    horizon_id: NonEmptyStr
    stage: ExecutionStage
    decision_time: datetime
    forecast_value: float | None = None
    signal_value: float | None = None
    target_quantity: float
    order_quantity: float
    fill_quantity: float
    benchmark_price: float | None = Field(default=None, gt=0.0)
    average_fill_price: float | None = Field(default=None, gt=0.0)
    fees: float = Field(ge=0.0)
    margin_used: float = Field(ge=0.0)
    pnl: float | None = None
    evidence_class: EvidenceClass

    @field_validator("decision_time")
    @classmethod
    def decision_time_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("decision_time must be UTC")
        return value

    @model_validator(mode="after")
    def validate_fill(self) -> "StageExecutionRecord":
        if self.fill_quantity == 0.0 and self.average_fill_price is not None:
            raise ValueError("no-fill record cannot have average_fill_price")
        if self.fill_quantity != 0.0 and self.average_fill_price is None:
            raise ValueError("filled record requires average_fill_price")
        if self.stage is ExecutionStage.LIVE and self.evidence_class not in {
            EvidenceClass.FACTUAL_EXECUTED,
            EvidenceClass.FACTUAL_OBSERVED_NOT_EXECUTED,
        }:
            raise ValueError("LIVE records require factual evidence class")
        return self


class PairwiseRealityGap(StrictModel):
    decision_id: NonEmptyStr
    policy_id: NonEmptyStr
    earlier_stage: ExecutionStage
    later_stage: ExecutionStage
    forecast_gap: float | None
    signal_gap: float | None
    order_quantity_gap: float
    fill_rate_earlier: float | None
    fill_rate_later: float | None
    fill_rate_gap: float | None
    slippage_bps_earlier: float | None
    slippage_bps_later: float | None
    slippage_gap_bps: float | None
    fee_gap: float
    margin_gap: float
    pnl_gap: float | None


class RealityGapPolicy(StrictModel):
    minimum_live_pairs: int = Field(default=20, ge=1)
    maximum_mean_abs_fill_rate_gap: float = Field(default=0.15, ge=0.0)
    maximum_mean_abs_slippage_gap_bps: float = Field(default=10.0, ge=0.0)
    maximum_mean_abs_pnl_gap: float | None = Field(default=None, ge=0.0)


class RealityGapResult(StrictModel):
    gaps: tuple[PairwiseRealityGap, ...]
    matched_live_pair_count: int = Field(ge=0)
    mean_abs_fill_rate_gap: float | None
    mean_abs_slippage_gap_bps: float | None
    mean_abs_pnl_gap: float | None
    state: TransportabilityState
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evaluate_reality_gap(
    records: tuple[StageExecutionRecord, ...],
    policy: RealityGapPolicy,
) -> RealityGapResult:
    """Match stages by decision and decompose transportability gaps."""

    grouped: dict[tuple[str, str], dict[ExecutionStage, StageExecutionRecord]] = defaultdict(dict)
    for record in records:
        key = (record.decision_id, record.policy_id)
        if record.stage in grouped[key]:
            raise ValueError("duplicate stage record for decision/policy")
        grouped[key][record.stage] = record

    gaps: list[PairwiseRealityGap] = []
    live_pairs: list[PairwiseRealityGap] = []
    for stages in grouped.values():
        for earlier, later in (
            (ExecutionStage.BACKTEST, ExecutionStage.SHADOW),
            (ExecutionStage.SHADOW, ExecutionStage.LIVE),
            (ExecutionStage.BACKTEST, ExecutionStage.LIVE),
        ):
            if earlier not in stages or later not in stages:
                continue
            gap = _pair_gap(stages[earlier], stages[later])
            gaps.append(gap)
            if later is ExecutionStage.LIVE:
                live_pairs.append(gap)

    fill_gaps = [abs(item.fill_rate_gap) for item in live_pairs if item.fill_rate_gap is not None]
    slippage_gaps = [
        abs(item.slippage_gap_bps) for item in live_pairs if item.slippage_gap_bps is not None
    ]
    pnl_gaps = [abs(item.pnl_gap) for item in live_pairs if item.pnl_gap is not None]
    mean_fill = fmean(fill_gaps) if fill_gaps else None
    mean_slippage = fmean(slippage_gaps) if slippage_gaps else None
    mean_pnl = fmean(pnl_gaps) if pnl_gaps else None
    reasons: list[str] = []

    if len(live_pairs) < policy.minimum_live_pairs:
        state = TransportabilityState.SHADOW_EVIDENCE_INSUFFICIENT
        reasons.append("P9_LIVE_REALITY_GAP_COHORT_UNMATCHED")
    else:
        fill_bad = mean_fill is not None and mean_fill > policy.maximum_mean_abs_fill_rate_gap
        slippage_bad = (
            mean_slippage is not None
            and mean_slippage > policy.maximum_mean_abs_slippage_gap_bps
        )
        pnl_bad = (
            policy.maximum_mean_abs_pnl_gap is not None
            and mean_pnl is not None
            and mean_pnl > policy.maximum_mean_abs_pnl_gap
        )
        if fill_bad or slippage_bad:
            state = TransportabilityState.EXECUTION_MODEL_MISSPECIFIED
            reasons.append("P9_LIVE_REALITY_GAP_MATERIAL")
        elif pnl_bad:
            state = TransportabilityState.SIMULATION_BIAS_DETECTED
            reasons.append("P9_LIVE_REALITY_GAP_MATERIAL")
        elif any(item.slippage_gap_bps is None for item in live_pairs):
            state = TransportabilityState.TRANSPORTABLE_WITH_LIMITATIONS
            reasons.append("P9_LIVE_EXECUTION_BENCHMARK_INVALID")
        else:
            state = TransportabilityState.TRANSPORTABLE

    payload = {
        "gaps": [item.model_dump(mode="json") for item in gaps],
        "state": state,
        "reason_codes": reasons,
    }
    return RealityGapResult(
        gaps=tuple(gaps),
        matched_live_pair_count=len(live_pairs),
        mean_abs_fill_rate_gap=mean_fill,
        mean_abs_slippage_gap_bps=mean_slippage,
        mean_abs_pnl_gap=mean_pnl,
        state=state,
        reason_codes=tuple(reasons),
        result_sha256=payload_sha256(payload),
    )


def _pair_gap(
    earlier: StageExecutionRecord,
    later: StageExecutionRecord,
) -> PairwiseRealityGap:
    if (
        earlier.cohort_id,
        earlier.instrument_id,
        earlier.horizon_id,
    ) != (
        later.cohort_id,
        later.instrument_id,
        later.horizon_id,
    ):
        raise ValueError("P9_LIVE_REALITY_GAP_COHORT_UNMATCHED")
    fill_rate_earlier = _fill_rate(earlier)
    fill_rate_later = _fill_rate(later)
    slippage_earlier = _slippage_bps(earlier)
    slippage_later = _slippage_bps(later)
    return PairwiseRealityGap(
        decision_id=earlier.decision_id,
        policy_id=earlier.policy_id,
        earlier_stage=earlier.stage,
        later_stage=later.stage,
        forecast_gap=_difference(later.forecast_value, earlier.forecast_value),
        signal_gap=_difference(later.signal_value, earlier.signal_value),
        order_quantity_gap=later.order_quantity - earlier.order_quantity,
        fill_rate_earlier=fill_rate_earlier,
        fill_rate_later=fill_rate_later,
        fill_rate_gap=_difference(fill_rate_later, fill_rate_earlier),
        slippage_bps_earlier=slippage_earlier,
        slippage_bps_later=slippage_later,
        slippage_gap_bps=_difference(slippage_later, slippage_earlier),
        fee_gap=later.fees - earlier.fees,
        margin_gap=later.margin_used - earlier.margin_used,
        pnl_gap=_difference(later.pnl, earlier.pnl),
    )


def _fill_rate(record: StageExecutionRecord) -> float | None:
    if record.order_quantity == 0.0:
        return None
    return record.fill_quantity / record.order_quantity


def _slippage_bps(record: StageExecutionRecord) -> float | None:
    if record.benchmark_price is None or record.average_fill_price is None:
        return None
    direction = 1.0 if record.order_quantity >= 0.0 else -1.0
    price_difference = record.average_fill_price - record.benchmark_price
    return direction * price_difference / record.benchmark_price * 1e4


def _difference(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return later - earlier
