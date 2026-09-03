"""Request/result contracts for all 34 public research-tool operations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from ..core.models import NonEmptyStr, ResearchToolModel

ModeId = Annotated[str, Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")]
PositiveLimit = Annotated[int, Field(ge=1, le=100_000)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ToolRequestBase(ResearchToolModel):
    research_mode: ModeId


class EvidenceRecord(ResearchToolModel):
    record_id: NonEmptyStr
    subject_id: str | None = None
    source_id: NonEmptyStr
    available_at: AwareDatetime
    values: dict[str, JsonValue] = Field(default_factory=dict)


class ToolResultBase(ResearchToolModel):
    records: tuple[EvidenceRecord, ...] = ()
    truncated: bool = False
    warnings: tuple[NonEmptyStr, ...] = ()


# Corpus
class CorpusSearchRequest(ToolRequestBase):
    query: NonEmptyStr
    entity_ids: tuple[NonEmptyStr, ...] = ()
    document_types: tuple[NonEmptyStr, ...] = ()
    source_ids: tuple[NonEmptyStr, ...] = ()
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    max_results: PositiveLimit = 20


class CorpusSearchResult(ToolResultBase):
    total_matches: Annotated[int, Field(ge=0)] = 0
    query_variants: tuple[NonEmptyStr, ...] = ()


class GetDocumentRequest(ToolRequestBase):
    document_id: NonEmptyStr
    section_ids: tuple[NonEmptyStr, ...] = ()
    include_full_text: bool = False


class GetDocumentResult(ToolResultBase):
    document_id: NonEmptyStr
    document_hash: NonEmptyStr


class CompareVersionsRequest(ToolRequestBase):
    document_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2, max_length=20)]
    section_ids: tuple[NonEmptyStr, ...] = ()


class CompareVersionsResult(ToolResultBase):
    version_order: tuple[NonEmptyStr, ...]
    changed_paths: tuple[NonEmptyStr, ...] = ()


class FindCounterevidenceRequest(ToolRequestBase):
    proposition: NonEmptyStr
    entity_ids: tuple[NonEmptyStr, ...] = ()
    document_types: tuple[NonEmptyStr, ...] = ()
    max_results: PositiveLimit = 20


class FindCounterevidenceResult(ToolResultBase):
    proposition_hash: NonEmptyStr
    counterevidence_count: Annotated[int, Field(ge=0)] = 0


class BuildTimelineRequest(ToolRequestBase):
    subject_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    event_types: tuple[NonEmptyStr, ...] = ()
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    max_events: PositiveLimit = 100


class BuildTimelineResult(ToolResultBase):
    event_count: Annotated[int, Field(ge=0)] = 0
    causal_claims_are_hypotheses: Literal[True] = True


class InspectProvenanceRequest(ToolRequestBase):
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]


class InspectProvenanceResult(ToolResultBase):
    chain_count: Annotated[int, Field(ge=0)] = 0


# Market
class MarketSnapshotRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    fields: tuple[NonEmptyStr, ...] = ()


class MarketSnapshotResult(ToolResultBase):
    instrument_count: Annotated[int, Field(ge=0)] = 0


class MarketHistoryRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    frequency: NonEmptyStr
    fields: tuple[NonEmptyStr, ...] = ("close",)

    @model_validator(mode="after")
    def ordered_window(self) -> "MarketHistoryRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class MarketHistoryResult(ToolResultBase):
    frequency: NonEmptyStr
    instrument_count: Annotated[int, Field(ge=0)] = 0


class MarketLiquidityRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    lookback_observations: PositiveLimit = 60
    frequency: NonEmptyStr = "1d"
    metrics: tuple[NonEmptyStr, ...] = ("volume", "turnover")


class MarketLiquidityResult(ToolResultBase):
    metrics_computed: tuple[NonEmptyStr, ...] = ()


class CorporateActionsRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    action_types: tuple[NonEmptyStr, ...] = ()


class CorporateActionsResult(ToolResultBase):
    action_count: Annotated[int, Field(ge=0)] = 0


class CompareInstrumentsRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2, max_length=50)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    metrics: tuple[NonEmptyStr, ...] = ("return", "volatility")
    normalization: Literal["NONE", "BASE_100", "ZSCORE_HISTORY_ONLY"] = "BASE_100"

    @model_validator(mode="after")
    def ordered_window(self) -> "CompareInstrumentsRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class CompareInstrumentsResult(ToolResultBase):
    metrics_computed: tuple[NonEmptyStr, ...] = ()


# Options
class GetOptionContractsRequest(ToolRequestBase):
    underlying_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    expiry_from: AwareDatetime | None = None
    expiry_to: AwareDatetime | None = None
    option_types: tuple[Literal["CALL", "PUT"], ...] = ()

    @model_validator(mode="after")
    def ordered_window(self) -> "GetOptionContractsRequest":
        if self.expiry_from is not None and self.expiry_to is not None and self.expiry_from > self.expiry_to:
            raise ValueError("expiry_from must not exceed expiry_to")
        return self


class GetOptionContractsResult(ToolResultBase):
    contract_count: Annotated[int, Field(ge=0)] = 0


class GetOptionChainSnapshotRequest(ToolRequestBase):
    underlying_id: NonEmptyStr
    expiry_dates: tuple[NonEmptyStr, ...] = ()
    strikes: tuple[float, ...] = ()
    include_greeks_if_observed: bool = False


class GetOptionChainSnapshotResult(ToolResultBase):
    contract_count: Annotated[int, Field(ge=0)] = 0
    historical_snapshot_required: Literal[True] = True


class GetOptionQuoteHistoryRequest(ToolRequestBase):
    contract_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=200)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    frequency: NonEmptyStr

    @model_validator(mode="after")
    def ordered_window(self) -> "GetOptionQuoteHistoryRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class GetOptionQuoteHistoryResult(ToolResultBase):
    contract_count: Annotated[int, Field(ge=0)] = 0


class OptionSurfaceDiagnosticsRequest(ToolRequestBase):
    underlying_id: NonEmptyStr
    expiry_dates: tuple[NonEmptyStr, ...] = ()
    diagnostics: tuple[NonEmptyStr, ...] = ("skew", "term_structure")
    minimum_quote_count: PositiveLimit = 10


class OptionSurfaceDiagnosticsResult(ToolResultBase):
    diagnostics_computed: tuple[NonEmptyStr, ...] = ()
    coverage_score: Probability = 0.0


# Macro
class SearchMacroSeriesRequest(ToolRequestBase):
    query: NonEmptyStr
    regions: tuple[NonEmptyStr, ...] = ()
    categories: tuple[NonEmptyStr, ...] = ()
    max_results: PositiveLimit = 20


class SearchMacroSeriesResult(ToolResultBase):
    series_count: Annotated[int, Field(ge=0)] = 0


class GetMacroObservationsRequest(ToolRequestBase):
    series_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    transformations: tuple[NonEmptyStr, ...] = ()
    vintage_policy: Literal[
        "KNOWN_AT_DECISION_TIME",
        "ORIGINAL_RELEASE",
        "LATEST_KNOWN_AT_DECISION_TIME",
    ] = "KNOWN_AT_DECISION_TIME"

    @model_validator(mode="after")
    def ordered_window(self) -> "GetMacroObservationsRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class GetMacroObservationsResult(ToolResultBase):
    series_count: Annotated[int, Field(ge=0)] = 0
    vintage_policy: NonEmptyStr


class GetMacroReleaseSnapshotRequest(ToolRequestBase):
    release_ids: tuple[NonEmptyStr, ...] = ()
    series_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def at_least_one_selector(self) -> "GetMacroReleaseSnapshotRequest":
        if not self.release_ids and not self.series_ids:
            raise ValueError("release_ids or series_ids is required")
        return self


class GetMacroReleaseSnapshotResult(ToolResultBase):
    release_count: Annotated[int, Field(ge=0)] = 0


class CompareMacroSeriesRequest(ToolRequestBase):
    series_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2, max_length=100)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    normalization: Literal["NONE", "INDEX_100", "ZSCORE_HISTORY_ONLY"] = "NONE"

    @model_validator(mode="after")
    def ordered_window(self) -> "CompareMacroSeriesRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class CompareMacroSeriesResult(ToolResultBase):
    series_count: Annotated[int, Field(ge=0)] = 0


class GetAssetMacroContextRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    factor_categories: tuple[NonEmptyStr, ...] = ()
    lookback_observations: PositiveLimit = 120


class GetAssetMacroContextResult(ToolResultBase):
    factor_count: Annotated[int, Field(ge=0)] = 0
    signal_authority: Literal[False] = False


# Company
class GetCompanyProfileRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    sections: tuple[NonEmptyStr, ...] = ()


class GetCompanyProfileResult(ToolResultBase):
    entity_count: Annotated[int, Field(ge=0)] = 0


class GetFinancialStatementsRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    statement_types: tuple[Literal["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"], ...] = ()
    period_count: PositiveLimit = 8
    basis: Literal["AS_REPORTED", "LATEST_KNOWN_AT_DECISION_TIME"] = "AS_REPORTED"


class GetFinancialStatementsResult(ToolResultBase):
    statement_count: Annotated[int, Field(ge=0)] = 0
    restatements_preserved: Literal[True] = True


class GetFundamentalSnapshotRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    metrics: tuple[NonEmptyStr, ...] = ()
    period_count: PositiveLimit = 8


class GetFundamentalSnapshotResult(ToolResultBase):
    metrics_computed: tuple[NonEmptyStr, ...] = ()


class GetGuidanceRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    metrics: tuple[NonEmptyStr, ...] = ()
    horizons: tuple[NonEmptyStr, ...] = ()


class GetGuidanceResult(ToolResultBase):
    guidance_count: Annotated[int, Field(ge=0)] = 0


class GetCapitalAllocationRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    period_count: PositiveLimit = 10
    categories: tuple[NonEmptyStr, ...] = ()


class GetCapitalAllocationResult(ToolResultBase):
    event_count: Annotated[int, Field(ge=0)] = 0


class GetPeersRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=50)]
    dimensions: tuple[NonEmptyStr, ...] = ()
    max_peers: Annotated[int, Field(ge=1, le=100)] = 20


class GetPeersResult(ToolResultBase):
    peer_count: Annotated[int, Field(ge=0)] = 0
    authority: Literal["DOCUMENTED_OR_EXPLICITLY_SUGGESTED"] = "DOCUMENTED_OR_EXPLICITLY_SUGGESTED"


class CalculateValuationRequest(ToolRequestBase):
    entity_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=20)]
    method: Literal["MULTIPLES", "HISTORICAL_BANDS", "PEER_BANDS", "SCENARIO_DCF", "REVERSE_DCF"]
    assumptions: dict[str, JsonValue] = Field(default_factory=dict)
    currency: NonEmptyStr


class CalculateValuationResult(ToolResultBase):
    method: NonEmptyStr
    assumptions_echo: dict[str, JsonValue] = Field(default_factory=dict)
    optimization_performed: Literal[False] = False


# Quant
class InstrumentWindowRequest(ToolRequestBase):
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    start_time: AwareDatetime
    end_time: AwareDatetime
    frequency: NonEmptyStr

    @model_validator(mode="after")
    def ordered_window(self) -> "InstrumentWindowRequest":
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self


class ReturnStatisticsRequest(InstrumentWindowRequest):
    metrics: tuple[NonEmptyStr, ...] = ("mean", "standard_deviation")


class ReturnStatisticsResult(ToolResultBase):
    metrics_computed: tuple[NonEmptyStr, ...] = ()


class RealizedVolatilityRequest(ToolRequestBase):
    instrument_ids: tuple[NonEmptyStr, ...] = ()
    returns: tuple[float, ...] = ()
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    frequency: str | None = None
    estimator: NonEmptyStr = "standard_deviation"
    annualization_factor: Annotated[float, Field(gt=0.0)] = 252.0

    @model_validator(mode="after")
    def source_is_unambiguous(self) -> "RealizedVolatilityRequest":
        by_ids = bool(self.instrument_ids)
        by_returns = bool(self.returns)
        if by_ids == by_returns:
            raise ValueError("provide exactly one of instrument_ids or returns")
        if by_ids and (self.start_time is None or self.end_time is None or self.frequency is None):
            raise ValueError("instrument query requires start_time, end_time and frequency")
        if self.start_time is not None and self.end_time is not None and self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        if len(self.returns) == 1:
            raise ValueError("returns requires at least two observations")
        return self


class RealizedVolatilityResult(ToolResultBase):
    realized_volatility: Annotated[float, Field(ge=0.0)]
    estimator: NonEmptyStr


class DrawdownRequest(InstrumentWindowRequest):
    include_recovery: bool = True


class DrawdownResult(ToolResultBase):
    maximum_drawdown: Annotated[float, Field(le=0.0)]


class CorrelationRequest(InstrumentWindowRequest):
    method: Literal["PEARSON", "SPEARMAN"] = "PEARSON"
    rolling_window: int | None = Field(default=None, ge=2, le=10_000)


class CorrelationResult(ToolResultBase):
    method: NonEmptyStr


class EntropyRequest(InstrumentWindowRequest):
    method: Literal["SHANNON", "PERMUTATION"] = "SHANNON"
    bins: int | None = Field(default=None, ge=2, le=1_000)


class EntropyResult(ToolResultBase):
    method: NonEmptyStr
    discretization_version: NonEmptyStr


class EventWindowRequest(ToolRequestBase):
    event_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    instrument_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=100)]
    pre_observations: Annotated[int, Field(ge=0, le=10_000)]
    post_observations: Annotated[int, Field(ge=0, le=10_000)]
    frequency: NonEmptyStr
    benchmark_id: str | None = None


class EventWindowResult(ToolResultBase):
    event_count: Annotated[int, Field(ge=0)] = 0
    causal_claim: Literal[False] = False


class ScenarioShockRequest(ToolRequestBase):
    exposures: dict[str, float]
    shocks: dict[str, float]
    relationships: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def non_empty_inputs(self) -> "ScenarioShockRequest":
        if not self.exposures or not self.shocks:
            raise ValueError("exposures and shocks must be non-empty")
        return self


class ScenarioShockResult(ToolResultBase):
    scenario_values: dict[str, float]
    probability_estimated: Literal[False] = False


OPERATION_MODELS: dict[tuple[str, str], tuple[type[ResearchToolModel], type[ResearchToolModel]]] = {
    ("research.corpus.v1", "search"): (CorpusSearchRequest, CorpusSearchResult),
    ("research.corpus.v1", "get_document"): (GetDocumentRequest, GetDocumentResult),
    ("research.corpus.v1", "compare_versions"): (CompareVersionsRequest, CompareVersionsResult),
    ("research.corpus.v1", "find_counterevidence"): (FindCounterevidenceRequest, FindCounterevidenceResult),
    ("research.corpus.v1", "build_timeline"): (BuildTimelineRequest, BuildTimelineResult),
    ("research.corpus.v1", "inspect_provenance"): (InspectProvenanceRequest, InspectProvenanceResult),
    ("market.observation.v1", "get_snapshot"): (MarketSnapshotRequest, MarketSnapshotResult),
    ("market.observation.v1", "get_history"): (MarketHistoryRequest, MarketHistoryResult),
    ("market.observation.v1", "get_liquidity"): (MarketLiquidityRequest, MarketLiquidityResult),
    ("market.observation.v1", "get_corporate_actions"): (CorporateActionsRequest, CorporateActionsResult),
    ("market.observation.v1", "compare_instruments"): (CompareInstrumentsRequest, CompareInstrumentsResult),
    ("options.observation.v1", "get_contracts"): (GetOptionContractsRequest, GetOptionContractsResult),
    ("options.observation.v1", "get_chain_snapshot"): (GetOptionChainSnapshotRequest, GetOptionChainSnapshotResult),
    ("options.observation.v1", "get_quote_history"): (GetOptionQuoteHistoryRequest, GetOptionQuoteHistoryResult),
    ("options.observation.v1", "get_surface_diagnostics"): (OptionSurfaceDiagnosticsRequest, OptionSurfaceDiagnosticsResult),
    ("macro.observation.v1", "search_series"): (SearchMacroSeriesRequest, SearchMacroSeriesResult),
    ("macro.observation.v1", "get_observations"): (GetMacroObservationsRequest, GetMacroObservationsResult),
    ("macro.observation.v1", "get_release_snapshot"): (GetMacroReleaseSnapshotRequest, GetMacroReleaseSnapshotResult),
    ("macro.observation.v1", "compare_series"): (CompareMacroSeriesRequest, CompareMacroSeriesResult),
    ("macro.observation.v1", "get_asset_context"): (GetAssetMacroContextRequest, GetAssetMacroContextResult),
    ("company.fundamentals.v1", "get_profile"): (GetCompanyProfileRequest, GetCompanyProfileResult),
    ("company.fundamentals.v1", "get_financial_statements"): (GetFinancialStatementsRequest, GetFinancialStatementsResult),
    ("company.fundamentals.v1", "get_fundamental_snapshot"): (GetFundamentalSnapshotRequest, GetFundamentalSnapshotResult),
    ("company.fundamentals.v1", "get_guidance"): (GetGuidanceRequest, GetGuidanceResult),
    ("company.fundamentals.v1", "get_capital_allocation"): (GetCapitalAllocationRequest, GetCapitalAllocationResult),
    ("company.fundamentals.v1", "get_peers"): (GetPeersRequest, GetPeersResult),
    ("company.fundamentals.v1", "calculate_valuation"): (CalculateValuationRequest, CalculateValuationResult),
    ("quant.diagnostics.v1", "return_statistics"): (ReturnStatisticsRequest, ReturnStatisticsResult),
    ("quant.diagnostics.v1", "realized_volatility"): (RealizedVolatilityRequest, RealizedVolatilityResult),
    ("quant.diagnostics.v1", "drawdown"): (DrawdownRequest, DrawdownResult),
    ("quant.diagnostics.v1", "correlation"): (CorrelationRequest, CorrelationResult),
    ("quant.diagnostics.v1", "entropy"): (EntropyRequest, EntropyResult),
    ("quant.diagnostics.v1", "event_window"): (EventWindowRequest, EventWindowResult),
    ("quant.diagnostics.v1", "scenario_shock"): (ScenarioShockRequest, ScenarioShockResult),
}
