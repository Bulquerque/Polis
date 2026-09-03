from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date

from pydantic import JsonValue

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.options.surface import (
    build_surface_summary,
)

from .evidence import build_coverage, build_envelope, build_pit_proof, evidence_ref
from .normalization import optional_float, parse_date, parse_datetime
from .ports import PitMarketQueryPort, VisibleRecordBatch
from .request_contracts import (
    GetChainSnapshotRequest,
    GetContractsRequest,
    GetQuoteHistoryRequest,
    GetSurfaceDiagnosticsRequest,
    MarketToolCallContext,
)
from .result_contracts import (
    MarketDerivativesToolResultEnvelope,
    OptionContractObservation,
    OptionQuoteObservation,
)
from .types import OptionMode, OptionType, OutcomeStatus, SurfaceDiagnosticStatus


class OptionObservationHandlers:
    def __init__(self, boundary: PitMarketQueryPort) -> None:
        self._boundary = boundary

    async def get_contracts(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetContractsRequest.model_validate(arguments, strict=False)
        batch = self._boundary.query(
            "clean_option_contract_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.underlying},
        )
        rows = tuple(row for row in batch.rows if self._contract_matches(row, request, context))
        rows = rows[: request.max_records]
        if not rows:
            return self._empty("get_contracts", request.research_mode.value, context, (batch,))
        observations = tuple(self._contract(row) for row in rows)
        evidence = tuple(
            evidence_ref(
                "clean_option_contract_panel",
                row,
                key_fields=("contract_key", "first_seen_date", "source_id"),
            )
            for row in rows
        )
        return self._envelope(
            operation_id="get_contracts",
            mode=request.research_mode.value,
            context=context,
            batches=(batch,),
            records=tuple(item.model_dump(mode="json") for item in observations),
            evidence=evidence,
            truncated=len(rows) == request.max_records and len(batch.rows) > len(rows),
            work_units=max(1, len(rows)),
        )

    async def get_chain_snapshot(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetChainSnapshotRequest.model_validate(arguments, strict=False)
        contracts, quotes, batches = self._chain_rows(request, context)
        latest = self._latest_quote_by_contract(quotes)
        joined = [
            (contract, latest[str(contract.get("contract_key"))])
            for contract in contracts
            if str(contract.get("contract_key")) in latest
        ]
        if request.executable_only:
            joined = [pair for pair in joined if str(pair[1].get("execution_status") or "").upper() == "EXECUTABLE"]
        joined = joined[: request.max_records]
        if not joined:
            return self._empty("get_chain_snapshot", request.research_mode.value, context, batches)
        observations = tuple(self._quote(quote, contract) for contract, quote in joined)
        evidence = tuple(
            item
            for contract, quote in joined
            for item in (
                evidence_ref(
                    "clean_option_contract_panel",
                    contract,
                    key_fields=("contract_key", "first_seen_date", "source_id"),
                ),
                evidence_ref(
                    "clean_option_quotes_panel",
                    quote,
                    key_fields=("contract_key", "date", "source_id"),
                ),
            )
        )
        return self._envelope(
            operation_id="get_chain_snapshot",
            mode=request.research_mode.value,
            context=context,
            batches=batches,
            records=tuple(item.model_dump(mode="json") for item in observations),
            evidence=evidence,
            truncated=len(joined) == request.max_records,
            work_units=max(1, len(joined)),
        )

    async def get_quote_history(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetQuoteHistoryRequest.model_validate(arguments, strict=False)
        quote_batch = self._boundary.query(
            "clean_option_quotes_panel",
            decision_time=context.decision_time,
            filters={"contract_key": request.contract_keys},
        )
        contract_batch = self._boundary.query(
            "clean_option_contract_panel",
            decision_time=context.decision_time,
            filters={"contract_key": request.contract_keys},
        )
        contracts = {str(row.get("contract_key")): row for row in contract_batch.rows}
        grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in quote_batch.rows:
            if not self._date_matches(row, request.start_date, request.end_date):
                continue
            grouped[str(row.get("contract_key"))].append(row)
        selected = tuple(
            row
            for key in sorted(grouped)
            for row in sorted(grouped[key], key=lambda item: str(item.get("available_at") or ""))[
                -request.max_records_per_contract :
            ]
        )
        if not selected:
            return self._empty(
                "get_quote_history",
                request.research_mode.value,
                context,
                (quote_batch, contract_batch),
            )
        observations = tuple(
            self._quote(row, contracts.get(str(row.get("contract_key")))) for row in selected
        )
        evidence = tuple(
            evidence_ref(
                "clean_option_quotes_panel",
                row,
                key_fields=("contract_key", "date", "source_id"),
            )
            for row in selected
        )
        return self._envelope(
            operation_id="get_quote_history",
            mode=request.research_mode.value,
            context=context,
            batches=(quote_batch, contract_batch),
            records=tuple(item.model_dump(mode="json") for item in observations),
            evidence=evidence,
            truncated=any(len(rows) > request.max_records_per_contract for rows in grouped.values()),
            work_units=max(1, len(selected)),
        )

    async def get_surface_diagnostics(
        self,
        arguments: Mapping[str, JsonValue],
        context: MarketToolCallContext,
    ) -> MarketDerivativesToolResultEnvelope:
        request = GetSurfaceDiagnosticsRequest.model_validate(arguments, strict=False)
        chain_request = GetChainSnapshotRequest(
            underlying=request.underlying,
            option_type=request.option_type,
            research_mode=OptionMode.SURFACE_ANALYSIS,
            executable_only=request.executable_only,
            max_records=10000,
        )
        contracts, quotes, chain_batches = self._chain_rows(chain_request, context)
        # A current chain source can provide executable bid/ask/last values
        # without IV.  Surface diagnostics must select the latest quote that
        # actually observes IV; otherwise a valid older IV observation is
        # hidden by a newer, IV-less snapshot and the operation blocks.
        latest = self._latest_quote_by_contract(quotes, require_observed_iv=True)
        joined = [
            (contract, latest[str(contract.get("contract_key"))])
            for contract in contracts
            if str(contract.get("contract_key")) in latest
        ]
        if request.expiration_dates:
            allowed = set(request.expiration_dates)
            joined = [
                pair
                for pair in joined
                if parse_date(pair[0].get("expiration_date"), field="expiration_date") in allowed
            ]
        quote_rows = [
            {**dict(contract), **dict(quote)}
            for contract, quote in joined
            if not request.executable_only
            or str(quote.get("execution_status") or "").upper() == "EXECUTABLE"
        ]
        underlying_batch = self._boundary.query(
            "clean_underlying_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.underlying},
        )
        spot = self._latest_spot(underlying_batch)
        batches = (*chain_batches, underlying_batch)
        observed_iv = any(
            row.get("iv") not in (None, "") or row.get("implied_volatility") not in (None, "")
            for row in quote_rows
        )
        if not observed_iv:
            return self._empty(
                "get_surface_diagnostics",
                request.research_mode.value,
                context,
                batches,
                missing=("OBSERVED_IV_UNAVAILABLE",),
                status=OutcomeStatus.BLOCKED_UPSTREAM,
            )
        summary = build_surface_summary(
            underlying=request.underlying,
            decision_time=context.decision_time,
            quote_rows=quote_rows,
            spot=spot,
            minimum_strikes_per_expiry=request.minimum_strikes_per_expiry,
        )
        evidence = tuple(
            evidence_ref(
                "clean_option_quotes_panel",
                quote,
                key_fields=("contract_key", "date", "source_id"),
            )
            for _, quote in joined
        )
        degraded = any(
            item.diagnostic_status is not SurfaceDiagnosticStatus.OBSERVED_IV
            for item in summary.slices
        )
        missing = tuple(summary.warnings)
        return self._envelope(
            operation_id="get_surface_diagnostics",
            mode=request.research_mode.value,
            context=context,
            batches=batches,
            records=(summary.model_dump(mode="json"),),
            evidence=evidence,
            missing=missing,
            status=OutcomeStatus.DEGRADED if degraded else OutcomeStatus.PASS,
            warnings=summary.warnings,
            work_units=max(1, len(quote_rows)),
        )

    def _chain_rows(
        self,
        request: GetChainSnapshotRequest,
        context: MarketToolCallContext,
    ) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...], tuple[VisibleRecordBatch, ...]]:
        contract_batch = self._boundary.query(
            "clean_option_contract_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.underlying},
        )
        quote_batch = self._boundary.query(
            "clean_option_quotes_panel",
            decision_time=context.decision_time,
            filters={"underlying": request.underlying},
        )
        contracts = tuple(
            row
            for row in contract_batch.rows
            if self._live_contract(row, context)
            and (request.expiration_date is None or parse_date(row.get("expiration_date"), field="expiration_date") == request.expiration_date)
            and (request.option_type is None or self._option_type(row.get("option_type")) is request.option_type)
        )
        keys = {str(row.get("contract_key")) for row in contracts}
        quotes = tuple(row for row in quote_batch.rows if str(row.get("contract_key")) in keys)
        return contracts, quotes, (contract_batch, quote_batch)

    def _envelope(
        self,
        *,
        operation_id: str,
        mode: str,
        context: MarketToolCallContext,
        batches: tuple[VisibleRecordBatch, ...],
        records: tuple[dict[str, JsonValue], ...],
        evidence: tuple,
        missing: tuple[str, ...] = (),
        status: OutcomeStatus = OutcomeStatus.PASS,
        warnings: tuple[str, ...] = (),
        truncated: bool = False,
        work_units: int = 1,
    ) -> MarketDerivativesToolResultEnvelope:
        coverage = build_coverage(
            batches,
            records_returned=len(records),
            unique_sources=len({item.source_id for item in evidence}),
            missing_dimensions=missing,
            truncated=truncated,
        )
        proof = build_pit_proof(batches, decision_time=context.decision_time)
        return build_envelope(
            tool_id="options.observation.v1",
            operation_id=operation_id,
            request_id=context.request_id,
            requested_mode=mode,
            executed_mode=mode,
            outcome_status=status,
            records=records,
            evidence_refs=evidence,
            coverage=coverage,
            pit_proof=proof,
            handler_id=f"p3.s36.options.{operation_id}",
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
        )

    @staticmethod
    def _contract_matches(
        row: Mapping[str, object],
        request: GetContractsRequest,
        context: MarketToolCallContext,
    ) -> bool:
        expiration = parse_date(row.get("expiration_date"), field="expiration_date")
        if not request.include_expired and expiration < context.decision_time.date():
            return False
        if request.expiration_from and expiration < request.expiration_from:
            return False
        if request.expiration_to and expiration > request.expiration_to:
            return False
        if request.option_type and OptionObservationHandlers._option_type(row.get("option_type")) is not request.option_type:
            return False
        return True

    @staticmethod
    def _live_contract(row: Mapping[str, object], context: MarketToolCallContext) -> bool:
        expiration = parse_date(row.get("expiration_date"), field="expiration_date")
        if expiration < context.decision_time.date():
            return False
        last_seen = row.get("last_seen_date")
        if last_seen not in (None, "") and parse_date(last_seen, field="last_seen_date") < context.decision_time.date():
            return False
        return True

    @staticmethod
    def _latest_quote_by_contract(
        rows: tuple[Mapping[str, object], ...],
        *,
        require_observed_iv: bool = False,
    ) -> dict[str, Mapping[str, object]]:
        output: dict[str, Mapping[str, object]] = {}
        for row in rows:
            if require_observed_iv and row.get("iv") in (None, "") and row.get("implied_volatility") in (None, ""):
                continue
            key = str(row.get("contract_key"))
            previous = output.get(key)
            if previous is None or parse_datetime(row.get("available_at"), field="available_at") > parse_datetime(previous.get("available_at"), field="available_at"):
                output[key] = row
        return output

    @staticmethod
    def _contract(row: Mapping[str, object]) -> OptionContractObservation:
        last_seen = row.get("last_seen_date")
        return OptionContractObservation(
            contract_key=str(row.get("contract_key") or "UNKNOWN"),
            option_id=str(row.get("option_id") or "UNKNOWN"),
            underlying=str(row.get("underlying") or "UNKNOWN"),
            option_type=OptionObservationHandlers._option_type(row.get("option_type")),
            strike=float(row.get("strike")),
            expiration_date=parse_date(row.get("expiration_date"), field="expiration_date"),
            contract_size=optional_float(row.get("contract_size"), field="contract_size", positive=True),
            first_seen_date=parse_date(row.get("first_seen_date"), field="first_seen_date"),
            last_seen_date=None if last_seen in (None, "") else parse_date(last_seen, field="last_seen_date"),
            source_id=str(row.get("source_id") or "UNKNOWN"),
            lineage_id=str(row.get("lineage_id") or "UNKNOWN"),
            quality_reasons=tuple(sorted(set(row.get("quality_reasons") or ()))),
        )

    @staticmethod
    def _quote(
        row: Mapping[str, object],
        contract: Mapping[str, object] | None,
    ) -> OptionQuoteObservation:
        merged = {**dict(contract or {}), **dict(row)}
        bid = optional_float(merged.get("bid"), field="bid", nonnegative=True)
        ask = optional_float(merged.get("ask"), field="ask", nonnegative=True)
        last = optional_float(merged.get("last_price"), field="last_price", nonnegative=True)
        mid = (bid + ask) / 2.0 if bid is not None and ask is not None and ask >= bid else None
        iv = optional_float(
            merged.get("iv") if merged.get("iv") not in (None, "") else merged.get("implied_volatility"),
            field="implied_volatility",
            nonnegative=True,
        )
        return OptionQuoteObservation(
            contract_key=str(merged.get("contract_key") or "UNKNOWN"),
            underlying=str(merged.get("underlying") or "UNKNOWN"),
            option_type=OptionObservationHandlers._option_type(merged.get("option_type")),
            strike=float(merged.get("strike")),
            expiration_date=parse_date(merged.get("expiration_date"), field="expiration_date"),
            observation_date=parse_date(merged.get("date"), field="date"),
            available_at=parse_datetime(merged.get("available_at"), field="available_at"),
            bid=bid,
            ask=ask,
            last_price=last,
            mid=mid,
            volume=optional_float(merged.get("volume"), field="volume", nonnegative=True),
            financial_volume=optional_float(
                merged.get("financial_volume"), field="financial_volume", nonnegative=True
            ),
            open_interest=optional_float(
                merged.get("open_interest"), field="open_interest", nonnegative=True
            ),
            implied_volatility=iv,
            execution_status=str(merged.get("execution_status") or "UNKNOWN"),
            source_id=str(merged.get("source_id") or "UNKNOWN"),
            lineage_id=str(merged.get("lineage_id") or "UNKNOWN"),
            quality_flag=str(merged.get("quality_flag") or "UNKNOWN"),
        )

    @staticmethod
    def _date_matches(
        row: Mapping[str, object],
        start: date | None,
        end: date | None,
    ) -> bool:
        observation = parse_date(row.get("date"), field="date")
        return not ((start and observation < start) or (end and observation > end))

    @staticmethod
    def _latest_spot(batch: VisibleRecordBatch) -> float | None:
        if not batch.rows:
            return None
        row = max(batch.rows, key=lambda item: parse_datetime(item.get("available_at"), field="available_at"))
        return optional_float(row.get("close"), field="close", nonnegative=True)

    @staticmethod
    def _option_type(value: object) -> OptionType:
        token = str(value or "UNKNOWN").upper()
        if token in {"CALL", "C"}:
            return OptionType.CALL
        if token in {"PUT", "P"}:
            return OptionType.PUT
        return OptionType.UNKNOWN
