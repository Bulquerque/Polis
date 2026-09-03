"""P9.S8 request and S7-S8 output bundle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation import (
    ProspectiveMonitoringBundle,
)
from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    IntegrityEnvelope,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import (
    S8BundleHeader,
    S8ModuleExecutionReceipt,
    S8SubphaseExecutionReceipt,
    S8UpstreamReferences,
)
from .m01_forecast_attribution import (
    ForecastAttributionPolicy,
    ForecastAttributionResult,
    ForecastComponentObservation,
)
from .m02_payoff_attribution import (
    CandidateOutcome,
    PayoffAttributionPolicy,
    PayoffAttributionResult,
    PayoffScenarioPoint,
)
from .m03_ranking_attribution import (
    RankingAttributionPolicy,
    RankingAttributionResult,
    RankingGroup,
)
from .m04_portfolio_attribution import (
    CandidateAllocationRecord,
    PhysicalPositionLedgerItem,
    PortfolioAttributionPolicy,
    PortfolioAttributionResult,
    VirtualCandidateLedgerItem,
)
from .m05_execution_attribution import (
    ExecutionAttributionPolicy,
    ExecutionAttributionResult,
    ExecutionRecord,
    LifecycleEvent,
)
from .m06_option_attribution import (
    OptionAttributionInterval,
    OptionAttributionPolicy,
    OptionAttributionResult,
)
from .m07_counterfactual import (
    CounterfactualPolicy,
    CounterfactualPolicyResult,
    LoggedPolicyObservation,
)
from .m08_reconciliation import (
    HierarchicalPnlAttributionResult,
    ReconciliationPolicy,
)


class S8ExecutionRequest(StrictModel):
    header: S8BundleHeader
    upstream: S8UpstreamReferences
    s7_bundle: ProspectiveMonitoringBundle
    forecast_observations: tuple[ForecastComponentObservation, ...]
    forecast_policy: ForecastAttributionPolicy
    payoff_scenario_points: tuple[PayoffScenarioPoint, ...]
    candidate_outcomes: tuple[CandidateOutcome, ...]
    payoff_policy: PayoffAttributionPolicy
    ranking_groups: tuple[RankingGroup, ...]
    ranking_policy: RankingAttributionPolicy
    allocation_records: tuple[CandidateAllocationRecord, ...]
    virtual_candidate_ledger: tuple[VirtualCandidateLedgerItem, ...]
    physical_position_ledger: tuple[PhysicalPositionLedgerItem, ...]
    portfolio_policy: PortfolioAttributionPolicy
    execution_records: tuple[ExecutionRecord, ...]
    lifecycle_events: tuple[LifecycleEvent, ...]
    execution_policy: ExecutionAttributionPolicy
    option_intervals: tuple[OptionAttributionInterval, ...]
    option_policy: OptionAttributionPolicy
    logged_policy_observations: tuple[LoggedPolicyObservation, ...]
    counterfactual_policy: CounterfactualPolicy
    factual_pnl: float
    reconciliation_policy: ReconciliationPolicy

    @model_validator(mode="after")
    def validate_scope(self) -> "S8ExecutionRequest":
        refs = (
            self.upstream.foundation_bundle,
            self.upstream.backtest_metrics_bundle,
            self.upstream.robustness_stress_bundle,
        )
        if any(
            ref.run_id != self.header.run_id or ref.cycle_id != self.header.cycle_id
            for ref in refs
        ):
            raise ValueError("upstream run_id/cycle_id must match S8 header")
        s7_header = self.s7_bundle.payload.header
        if s7_header.run_id != self.header.run_id or s7_header.cycle_id != self.header.cycle_id:
            raise ValueError("S7 and S8 bundles must share run_id/cycle_id")
        return self


class ProspectiveAttributionPayload(StrictModel):
    header: S8BundleHeader
    upstream_bundle_sha256s: tuple[str, str, str]
    s7_bundle_sha256: str
    forecast_attribution: ForecastAttributionResult
    payoff_attribution: PayoffAttributionResult
    ranking_attribution: RankingAttributionResult
    portfolio_attribution: PortfolioAttributionResult
    execution_attribution: ExecutionAttributionResult
    option_attribution: OptionAttributionResult
    counterfactual_report: CounterfactualPolicyResult
    hierarchical_reconciliation: HierarchicalPnlAttributionResult
    module_receipts: tuple[S8ModuleExecutionReceipt, ...]
    subphase_receipt: S8SubphaseExecutionReceipt
    limitations: tuple[NonEmptyStr, ...] = ()


class ProspectiveAttributionBundle(StrictModel):
    payload: ProspectiveAttributionPayload
    integrity: IntegrityEnvelope

    @model_validator(mode="after")
    def verify_integrity(self) -> "ProspectiveAttributionBundle":
        if payload_sha256(self.payload) != self.integrity.payload_sha256:
            raise ValueError("ProspectiveAttribution bundle integrity mismatch")
        return self


class Clock:
    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))

    def __call__(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("clock must return UTC datetime")
        return value
