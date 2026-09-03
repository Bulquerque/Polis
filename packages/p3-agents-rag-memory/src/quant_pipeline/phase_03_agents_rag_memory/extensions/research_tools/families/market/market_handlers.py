from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from statistics import mean, median

from pydantic import JsonValue

from .evidence import build_coverage, build_envelope, build_pit_proof, evidence_ref
from .normalization import optional_float, parse_date, parse_datetime
from .ports import PitMarketQueryPort, VisibleRecordBatch
from .request_contracts import (
    CompareInstrumentsRequest,
    GetCorporateActionsRequest,
    GetHistoryRequest,
    GetLiquidityRequest,
    GetSnapshotRequest,
    MarketToolCallContext,
)
from .result_contracts import (
    CorporateActionObservation,
    InstrumentComparisonObservation,
    LiquidityDiagnostic,
    MarketObservation,
    MarketDerivativesToolResultEnvelope,
)
from .types import AdjustmentPolicy, NormalizationPolicy, OutcomeStatus


class MarketObservationHandlers:
    def __init__(self, boundary: PitMarketQueryPort) -> None:
        self._boundary = boundary

    async def get_snapshot(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetSnapshotRequest.model_validate(arguments, strict=False)
        batch = self._boundary.query(
            "clean_underlying_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.instrument_id},
        )
        if not batch.rows:
            return self._empty("get_snapshot", request.research_mode.value, context, (batch,))
        row = max(batch.rows, key=lambda item: parse_datetime(item["available_at"], field="available_at"))
        observation = self._market_observation(row, context, AdjustmentPolicy.RAW)
        warnings: list[str] = []
        status = OutcomeStatus.PASS
        if request.max_staleness_seconds is not None:
            if observation.staleness_seconds > request.max_staleness_seconds:
                status = OutcomeStatus.DEGRADED
                warnings.append("P3_RT_DATA_STALE_OBSERVATION")
        return self._single_market_envelope(
            operation_id="get_snapshot",
            mode=request.research_mode.value,
            context=context,
            batch=batch,
            row=row,
            observation=observation,
            status=status,
            warnings=warnings,
        )

    async def get_history(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetHistoryRequest.model_validate(arguments, strict=False)
        batch = self._boundary.query(
            "clean_underlying_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.instrument_id},
        )
        selected = self._date_filter(batch.rows, request.start_date, request.end_date)
        selected = selected[-request.max_records :]
        if not selected:
            return self._empty("get_history", request.research_mode.value, context, (batch,))
        if request.adjustment_policy is not AdjustmentPolicy.RAW:
            unsupported = [row for row in selected if self._adjusted_close(row, request.adjustment_policy) is None]
            if unsupported:
                return self._blocked_adjustment(request, context, batch)
        observations = tuple(
            self._market_observation(row, context, request.adjustment_policy) for row in selected
        )
        records = tuple(item.model_dump(mode="json") for item in observations)
        evidence = tuple(
            evidence_ref(
                "clean_underlying_panel",
                row,
                key_fields=("underlying", "date", "source_id"),
            )
            for row in selected
        )
        return self._envelope(
            operation_id="get_history",
            mode=request.research_mode.value,
            context=context,
            batches=(batch,),
            records=records,
            evidence=evidence,
            missing=(),
            truncated=len(self._date_filter(batch.rows, request.start_date, request.end_date)) > len(selected),
            work_units=max(1, len(selected)),
        )

    async def get_liquidity(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetLiquidityRequest.model_validate(arguments, strict=False)
        batch = self._boundary.query(
            "clean_underlying_trade_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.instrument_id},
        )
        rows = tuple(sorted(batch.rows, key=lambda row: str(row.get("date") or "")))[-request.lookback_days :]
        if not rows:
            return self._empty("get_liquidity", request.research_mode.value, context, (batch,))
        diagnostic, missing = self._liquidity_diagnostic(request.instrument_id, rows)
        evidence = tuple(
            evidence_ref(
                "clean_underlying_trade_panel",
                row,
                key_fields=("underlying", "date", "source_id"),
            )
            for row in rows
        )
        return self._envelope(
            operation_id="get_liquidity",
            mode=request.research_mode.value,
            context=context,
            batches=(batch,),
            records=(diagnostic.model_dump(mode="json"),),
            evidence=evidence,
            missing=missing,
            truncated=len(batch.rows) > len(rows),
            status=OutcomeStatus.DEGRADED if missing else OutcomeStatus.PASS,
            warnings=tuple(f"P3_RT_DATA_{item}" for item in missing),
            work_units=max(1, len(rows)),
        )

    async def get_corporate_actions(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetCorporateActionsRequest.model_validate(arguments, strict=False)
        batch = self._boundary.query(
            "clean_corporate_actions_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.instrument_id},
        )
        rows = tuple(
            row
            for row in batch.rows
            if self._action_in_range(row, request.start_date, request.end_date)
        )
        if not rows:
            return self._empty("get_corporate_actions", request.research_mode.value, context, (batch,))
        observations = tuple(self._corporate_action(row) for row in rows)
        evidence = tuple(
            evidence_ref(
                "clean_corporate_actions_panel",
                row,
                key_fields=("underlying", "action_type", "effective_date", "source_id"),
            )
            for row in rows
        )
        return self._envelope(
            operation_id="get_corporate_actions",
            mode=request.research_mode.value,
            context=context,
            batches=(batch,),
            records=tuple(item.model_dump(mode="json") for item in observations),
            evidence=evidence,
            missing=(),
            work_units=max(1, len(rows)),
        )

    async def compare_instruments(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = CompareInstrumentsRequest.model_validate(arguments, strict=False)
        batches: list[VisibleRecordBatch] = []
        records: list[dict[str, JsonValue]] = []
        evidence = []
        missing: list[str] = []
        for instrument_id in request.instrument_ids:
            batch = self._boundary.query(
                "clean_underlying_panel",
                decision_time=context.decision_time,
                filters={"underlying": instrument_id},
            )
            batches.append(batch)
            rows = self._date_filter(batch.rows, request.start_date, request.end_date)
            rows = rows[-request.max_records_per_instrument :]
            if len(rows) < 2:
                missing.append(f"INSUFFICIENT_HISTORY:{instrument_id}")
                continue
            observation = self._comparison(instrument_id, rows, request.normalization)
            records.append(observation.model_dump(mode="json"))
            evidence.extend(
                evidence_ref(
                    "clean_underlying_panel",
                    row,
                    key_fields=("underlying", "date", "source_id"),
                )
                for row in rows
            )
        if not records:
            return self._empty(
                "compare_instruments",
                request.research_mode.value,
                context,
                tuple(batches),
                missing=tuple(missing),
                status=OutcomeStatus.BLOCKED_UPSTREAM,
            )
        return self._envelope(
            operation_id="compare_instruments",
            mode=request.research_mode.value,
            context=context,
            batches=tuple(batches),
            records=tuple(records),
            evidence=tuple(evidence),
            missing=tuple(missing),
            status=OutcomeStatus.DEGRADED if missing else OutcomeStatus.PASS,
            warnings=tuple(f"P3_RT_DATA_{item}" for item in missing),
            work_units=sum(len(batch.rows) for batch in batches),
        )

    def _single_market_envelope(
        self,
        *,
        operation_id: str,
        mode: str,
        context: MarketToolCallContext,
        batch: VisibleRecordBatch,
        row: Mapping[str, object],
        observation: MarketObservation,
        status: OutcomeStatus,
        warnings: list[str],
    ) -> MarketDerivativesToolResultEnvelope:
        return self._envelope(
            operation_id=operation_id,
            mode=mode,
            context=context,
            batches=(batch,),
            records=(observation.model_dump(mode="json"),),
            evidence=(
                evidence_ref(
                    "clean_underlying_panel",
                    row,
                    key_fields=("underlying", "date", "source_id"),
                ),
            ),
            missing=(),
            status=status,
            warnings=warnings,
            work_units=1,
        )

    def _envelope(
        self,
        *,
        operation_id: str,
        mode: str,
        context: MarketToolCallContext,
        batches: tuple[VisibleRecordBatch, ...],
        records: tuple[dict[str, JsonValue], ...],
        evidence: tuple,
        missing: tuple[str, ...],
        status: OutcomeStatus = OutcomeStatus.PASS,
        warnings: tuple[str, ...] | list[str] = (),
        truncated: bool = False,
        work_units: int = 1,
    ) -> MarketDerivativesToolResultEnvelope:
        sources = {item.source_id for item in evidence}
        coverage = build_coverage(
            batches,
            records_returned=len(records),
            unique_sources=len(sources),
            missing_dimensions=missing,
            truncated=truncated,
        )
        proof = build_pit_proof(batches, decision_time=context.decision_time)
        return build_envelope(
            tool_id="market.observation.v1",
            operation_id=operation_id,
            request_id=context.request_id,
            requested_mode=mode,
            executed_mode=mode,
            outcome_status=status,
            records=records,
            evidence_refs=evidence,
            coverage=coverage,
            pit_proof=proof,
            handler_id=f"p3.s36.market.{operation_id}",
            seed=context.deterministic_seed,
            internal_work_units=work_units,
            warnings=warnings,
        )

    def _empty(
        self,
        operation_id: str,
        mode: str,
        context: MarketToolCallContext,
        batches: tuple[VisibleRecordBatch, ...],
        *,
        missing: tuple[str, ...] = (),
        status: OutcomeStatus = OutcomeStatus.EMPTY_VALID,
    ) -> MarketDerivativesToolResultEnvelope:
        return self._envelope(
            operation_id=operation_id,
            mode=mode,
            context=context,
            batches=batches,
            records=(),
            evidence=(),
            missing=missing,
            status=status,
            work_units=1,
        )

    def _blocked_adjustment(
        self,
        request: GetHistoryRequest,
        context: MarketToolCallContext,
        batch: VisibleRecordBatch,
    ) -> MarketDerivativesToolResultEnvelope:
        return self._empty(
            "get_history",
            request.research_mode.value,
            context,
            (batch,),
            missing=(f"ADJUSTMENT_POLICY_UNAVAILABLE:{request.adjustment_policy.value}",),
            status=OutcomeStatus.BLOCKED_UPSTREAM,
        )

    @staticmethod
    def _market_observation(
        row: Mapping[str, object],
        context: MarketToolCallContext,
        policy: AdjustmentPolicy,
    ) -> MarketObservation:
        available = parse_datetime(row["available_at"], field="available_at")
        raw_close = optional_float(row.get("close"), field="close", nonnegative=True)
        if raw_close is None:
            raise ValueError("close is required")
        adjusted = MarketObservationHandlers._adjusted_close(row, policy)
        if adjusted is None:
            raise ValueError(f"adjustment policy unavailable: {policy.value}")
        return MarketObservation(
            instrument_id=str(row.get("underlying") or row.get("benchmark_id") or "UNKNOWN"),
            observation_date=parse_date(row.get("date"), field="date"),
            available_at=available,
            open=optional_float(row.get("open"), field="open", nonnegative=True),
            high=optional_float(row.get("high"), field="high", nonnegative=True),
            low=optional_float(row.get("low"), field="low", nonnegative=True),
            raw_close=raw_close,
            close=adjusted,
            adjustment_policy=policy.value,
            volume=optional_float(row.get("volume"), field="volume", nonnegative=True),
            financial_volume=optional_float(
                row.get("financial_volume"), field="financial_volume", nonnegative=True
            ),
            adjustment_factor=optional_float(
                row.get("adjustment_factor"), field="adjustment_factor", positive=True
            ),
            is_trading_day=row.get("is_trading_day") if isinstance(row.get("is_trading_day"), bool) else None,
            source_id=str(row.get("source_id") or "UNKNOWN"),
            lineage_id=str(row.get("lineage_id") or "UNKNOWN"),
            quality_flag=str(row.get("quality_flag") or "UNKNOWN"),
            staleness_seconds=max(0.0, (context.decision_time - available).total_seconds()),
        )

    @staticmethod
    def _adjusted_close(row: Mapping[str, object], policy: AdjustmentPolicy) -> float | None:
        raw = optional_float(row.get("close"), field="close", nonnegative=True)
        if raw is None:
            return None
        if policy is AdjustmentPolicy.RAW:
            return raw
        provider_policy = str(row.get("price_adjustment_policy") or "").upper()
        if policy is AdjustmentPolicy.PIT_SPLIT_ADJUSTED:
            explicit = optional_float(
                row.get("split_adjusted_close") or row.get("adjusted_close"),
                field="split_adjusted_close",
                nonnegative=True,
            )
            if explicit is not None:
                return explicit
            if provider_policy in {"SPLIT_ADJUSTED", "TOTAL_RETURN_ADJUSTED"}:
                return raw
            return None
        explicit = optional_float(
            row.get("total_return_close"), field="total_return_close", nonnegative=True
        )
        if explicit is not None:
            return explicit
        if provider_policy == "TOTAL_RETURN_ADJUSTED":
            return raw
        return None

    @staticmethod
    def _date_filter(
        rows: tuple[Mapping[str, object], ...],
        start: date | None,
        end: date | None,
    ) -> tuple[Mapping[str, object], ...]:
        selected = []
        for row in rows:
            observation_date = parse_date(row.get("date"), field="date")
            if start and observation_date < start:
                continue
            if end and observation_date > end:
                continue
            selected.append(row)
        return tuple(sorted(selected, key=lambda row: str(row.get("date") or "")))

    @staticmethod
    def _liquidity_diagnostic(
        instrument_id: str,
        rows: tuple[Mapping[str, object], ...],
    ) -> tuple[LiquidityDiagnostic, tuple[str, ...]]:
        volumes = [optional_float(row.get("volume"), field="volume", nonnegative=True) for row in rows]
        financial = [
            optional_float(row.get("financial_volume"), field="financial_volume", nonnegative=True)
            for row in rows
        ]
        spreads = []
        tradable = []
        scores = []
        for row in rows:
            bid = optional_float(row.get("bid"), field="bid", nonnegative=True)
            ask = optional_float(row.get("ask"), field="ask", nonnegative=True)
            if bid is not None and ask is not None and ask >= bid and ask + bid > 0:
                spreads.append((ask - bid) / ((ask + bid) / 2.0))
            if isinstance(row.get("tradability_flag"), bool):
                tradable.append(bool(row["tradability_flag"]))
            score = optional_float(row.get("liquidity_score"), field="liquidity_score", nonnegative=True)
            if score is not None:
                scores.append(score)
        known_volumes = [value for value in volumes if value is not None]
        known_financial = [value for value in financial if value is not None]
        missing: list[str] = []
        if not known_volumes:
            missing.append("VOLUME_UNAVAILABLE")
        if not spreads:
            missing.append("SPREAD_UNAVAILABLE")
        dates = [parse_date(row.get("date"), field="date") for row in rows]
        diagnostic = LiquidityDiagnostic(
            instrument_id=instrument_id,
            window_start=min(dates),
            window_end=max(dates),
            observations=len(rows),
            average_volume=mean(known_volumes) if known_volumes else None,
            median_volume=median(known_volumes) if known_volumes else None,
            average_financial_volume=mean(known_financial) if known_financial else None,
            average_relative_spread=mean(spreads) if spreads else None,
            latest_liquidity_score=scores[-1] if scores else None,
            tradable_fraction=(sum(tradable) / len(tradable)) if tradable else None,
            missing_volume_fraction=sum(value is None for value in volumes) / len(rows),
            missing_spread_fraction=1.0 - (len(spreads) / len(rows)),
            source_ids=tuple(sorted({str(row.get("source_id") or "UNKNOWN") for row in rows})),
        )
        return diagnostic, tuple(missing)

    @staticmethod
    def _corporate_action(row: Mapping[str, object]) -> CorporateActionObservation:
        def date_or_none(field: str) -> date | None:
            value = row.get(field)
            return None if value in (None, "") else parse_date(value, field=field)

        return CorporateActionObservation(
            instrument_id=str(row.get("underlying") or "UNKNOWN"),
            action_type=str(row.get("action_type") or "UNKNOWN"),
            available_at=parse_datetime(row.get("available_at"), field="available_at"),
            effective_date=date_or_none("effective_date"),
            ex_date=date_or_none("ex_date"),
            record_date=date_or_none("record_date"),
            payment_date=date_or_none("payment_date"),
            adjustment_factor=optional_float(
                row.get("adjustment_factor"), field="adjustment_factor", positive=True
            ),
            cash_amount=optional_float(
                row.get("cash_amount"), field="cash_amount", nonnegative=True
            ),
            ratio=optional_float(row.get("ratio"), field="ratio", positive=True),
            source_id=str(row.get("source_id") or "UNKNOWN"),
            lineage_id=str(row.get("lineage_id") or "UNKNOWN"),
        )

    @staticmethod
    def _action_in_range(
        row: Mapping[str, object],
        start: date | None,
        end: date | None,
    ) -> bool:
        value = row.get("effective_date") or row.get("ex_date")
        if value in (None, ""):
            return start is None and end is None
        action_date = parse_date(value, field="effective_date")
        return not ((start and action_date < start) or (end and action_date > end))

    @staticmethod
    def _comparison(
        instrument_id: str,
        rows: tuple[Mapping[str, object], ...],
        normalization: NormalizationPolicy,
    ) -> InstrumentComparisonObservation:
        first = optional_float(rows[0].get("close"), field="close", positive=True)
        last = optional_float(rows[-1].get("close"), field="close", nonnegative=True)
        if first is None or last is None:
            raise ValueError("comparison requires first and last close")
        cumulative = last / first - 1.0
        if normalization is NormalizationPolicy.NONE:
            normalized = last
        elif normalization is NormalizationPolicy.BASE_100:
            normalized = 100.0 * last / first
        else:
            normalized = cumulative
        return InstrumentComparisonObservation(
            instrument_id=instrument_id,
            start_date=parse_date(rows[0].get("date"), field="date"),
            end_date=parse_date(rows[-1].get("date"), field="date"),
            observation_count=len(rows),
            first_close=first,
            last_close=last,
            cumulative_return=cumulative,
            normalized_last_value=normalized,
            missing_trading_day_fraction=(
                sum(row.get("is_trading_day") is not True for row in rows) / len(rows)
            ),
            source_ids=tuple(sorted({str(row.get("source_id") or "UNKNOWN") for row in rows})),
        )
