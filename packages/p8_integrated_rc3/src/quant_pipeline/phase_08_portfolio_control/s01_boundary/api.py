"""Stable public API for P8.S1."""

from __future__ import annotations

from dataclasses import dataclass

from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.s1 import (
    M01Result,
    M02Result,
    M03Result,
    M04Result,
    M05Result,
    M06Result,
    P8DecisionSnapshot,
)

from .context import S1ExecutionContext
from .policies import S1Policy
from .ports import (
    AccountSnapshotPort,
    ArtifactStorePort,
    DebugBundleWriterPort,
    IdempotencyStorePort,
    PortfolioStateReaderPort,
)


@dataclass(frozen=True, slots=True)
class S1Ports:
    artifact_store: ArtifactStorePort
    idempotency_store: IdempotencyStorePort
    portfolio_state_reader: PortfolioStateReaderPort
    account_snapshot_port: AccountSnapshotPort
    debug_writer: DebugBundleWriterPort | None = None


@dataclass(frozen=True, slots=True)
class S1RunRequest:
    p7_handoff_bytes: bytes
    feedback_refs: tuple[ArtifactReference, ...]
    market_snapshot_ref: ArtifactReference
    context: S1ExecutionContext


@dataclass(frozen=True, slots=True)
class S1RunResult:
    m01: M01Result
    m02: M02Result
    m03: M03Result
    m04: M04Result
    m05: M05Result
    m06: M06Result

    @property
    def snapshot(self) -> P8DecisionSnapshot:
        return self.m06.snapshot


def run_s1(request: S1RunRequest, ports: S1Ports, policy: S1Policy | None = None) -> S1RunResult:
    """Execute the six S1 modules in their contract order."""

    from .orchestrator import run_s1_pipeline

    return run_s1_pipeline(request=request, ports=ports, policy=policy or S1Policy())
