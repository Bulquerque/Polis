"""S4 quality gate and S3-S4 publication contracts."""

from __future__ import annotations

from enum import StrEnum
from fnmatch import fnmatchcase
from typing import Self

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s03_backtest_tournament.common import (
    ArtifactReference,
    ModuleReceipt,
)

from .base_models import ModulePanelBase, QualifiedBacktestIdentity
from .common import (
    MetricRecord,
    NonEmptyStr,
    SemVer,
    Sha256,
    StrictModel,
    content_sha256,
)
from .distribution_models import DistributionEngineResult
from .drawdown_models import DrawdownResult
from .execution_models import ExecutionCapacityResult
from .factor_models import FactorRegressionResult
from .return_models import ReturnEngineResult
from .risk_adjusted_models import RiskAdjustedResult
from .tail_models import TailRiskResult


class QualityState(StrEnum):
    QUALIFIED = "QUALIFIED"
    QUALIFIED_WITH_LIMITATIONS = "QUALIFIED_WITH_LIMITATIONS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"


class MetricRegistryEntry(StrictModel):
    metric_pattern: NonEmptyStr
    metric_version: SemVer
    producer_module_id: NonEmptyStr
    unit: NonEmptyStr
    allowed_gross_net: tuple[NonEmptyStr, ...]


class MetricRegistry(StrictModel):
    registry_id: NonEmptyStr
    registry_version: SemVer
    entries: tuple[MetricRegistryEntry, ...]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        keys = [(entry.metric_pattern, entry.metric_version) for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate metric registry entries")
        expected = content_sha256(
            self.model_dump(mode="python", exclude={"content_sha256"})
        )
        if expected != self.content_sha256:
            raise ValueError("metric registry hash mismatch")
        return self

    def get(self, metric_id: str, version: str) -> MetricRegistryEntry:
        matches = [
            entry
            for entry in self.entries
            if entry.metric_version == version and fnmatchcase(metric_id, entry.metric_pattern)
        ]
        if not matches:
            raise KeyError(f"unknown metric {metric_id}@{version}")
        return max(matches, key=lambda entry: len(entry.metric_pattern.replace("*", "")))


class MetricQualityPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    money_tolerance: float = Field(default=1e-6, ge=0)
    require_factor_panel: bool = False
    require_all_core_metrics_qualified: bool = False


class MetricLimitation(StrictModel):
    metric_id: NonEmptyStr
    limitation: NonEmptyStr
    severity: NonEmptyStr


class MetricQualityReceipt(StrictModel):
    identity: QualifiedBacktestIdentity
    state: QualityState
    check_ids: tuple[NonEmptyStr, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    limitations: tuple[MetricLimitation, ...]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        expected = content_sha256(
            self.model_dump(mode="python", exclude={"content_sha256"})
        )
        if expected != self.content_sha256:
            raise ValueError("quality receipt hash mismatch")
        if self.state is QualityState.INVALID and not self.reason_codes:
            raise ValueError("invalid quality receipt requires reason codes")
        return self


class InstitutionalMetricPanel(ModulePanelBase):
    metric_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        if self.metric_count != len(self.metrics):
            raise ValueError("metric_count must equal metrics length")
        keys = [
            (metric.metric_id, metric.metric_version, metric.gross_net)
            for metric in self.metrics
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate metric identities")
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("institutional metric panel hash mismatch")
        return self


class MetricQualityRequest(StrictModel):
    returns: ReturnEngineResult
    distribution: DistributionEngineResult
    tails: TailRiskResult
    drawdowns: DrawdownResult
    risk_adjusted: RiskAdjustedResult
    factors: FactorRegressionResult | None
    execution: ExecutionCapacityResult
    registry: MetricRegistry
    policy: MetricQualityPolicy
    s3_subphase_receipt: ModuleReceipt | None = None
    s4_module_receipts: tuple[ModuleReceipt, ...] = ()


class MetricQualityResult(StrictModel):
    panel: InstitutionalMetricPanel
    receipt: MetricQualityReceipt


class BacktestMetricsBundle(StrictModel):
    bundle_id: NonEmptyStr
    bundle_version: SemVer
    identity: QualifiedBacktestIdentity
    s3_artifact_refs: tuple[ArtifactReference, ...]
    s4_artifact_refs: tuple[ArtifactReference, ...]
    metric_panel: InstitutionalMetricPanel
    quality_receipt: MetricQualityReceipt
    module_receipts: tuple[ModuleReceipt, ...]
    upstream_bundle_sha256: Sha256
    bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        modules = [receipt.module_id for receipt in self.module_receipts]
        expected_modules = {f"P9.S4.M{index:02d}" for index in range(1, 9)}
        if set(modules) != expected_modules or len(modules) != 8:
            raise ValueError("bundle requires exactly one receipt for each S4 module")
        expected = content_sha256(
            self.model_dump(mode="python", exclude={"bundle_sha256"})
        )
        if expected != self.bundle_sha256:
            raise ValueError("S3-S4 bundle hash mismatch")
        return self
