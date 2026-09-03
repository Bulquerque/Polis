
"""Stable public API for P8.S2."""

from __future__ import annotations

from dataclasses import dataclass

from quant_pipeline.phase_08_contracts.canonical import finalize_content_hash
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateTerminalStateLedger,
    P8DecisionSnapshot,
    PromotedPortfolioFeedbackContext,
    ResolvedCandidateEvidenceIndex,
    ValidatedP7HandoffBundle,
)
from quant_pipeline.phase_08_contracts.state import CurrentPortfolioAndAccountState

from .context import S2ExecutionContext
from .contracts.bundle import P8CandidateContextBundleV1, S2InputBundleV1
from .contracts.results import M01Result, M02Result, M03Result, M04Result, M05Result, M06Result, S2OutputResult
from .policies import S2Policy
from .ports import DebugBundleWriterPort


def build_s2_input_bundle(
    *,
    validated_handoff: ValidatedP7HandoffBundle,
    terminal_ledger: CandidateTerminalStateLedger,
    resolved_evidence: ResolvedCandidateEvidenceIndex,
    feedback_context: PromotedPortfolioFeedbackContext,
    current_state: CurrentPortfolioAndAccountState,
    snapshot: P8DecisionSnapshot,
) -> S2InputBundleV1:
    provisional = S2InputBundleV1(
        contract_version="P8_S2_INPUT_BUNDLE_V1",
        schema_version="1.0.0",
        validated_handoff=validated_handoff,
        terminal_ledger=terminal_ledger,
        resolved_evidence=resolved_evidence,
        feedback_context=feedback_context,
        current_state=current_state,
        snapshot=snapshot,
        content_sha256="0" * 64,
    )
    return finalize_content_hash(provisional)


@dataclass(frozen=True, slots=True)
class S2RunRequest:
    input_bundle: S2InputBundleV1
    context: S2ExecutionContext


@dataclass(frozen=True, slots=True)
class S2Ports:
    debug_writer: DebugBundleWriterPort | None = None


@dataclass(frozen=True, slots=True)
class S2RunResult:
    m01: M01Result
    m02: M02Result
    m03: M03Result
    m04: M04Result
    m05: M05Result
    m06: M06Result
    output: S2OutputResult

    @property
    def bundle(self) -> P8CandidateContextBundleV1:
        return self.output.bundle


def run_s2(request: S2RunRequest, ports: S2Ports | None = None, policy: S2Policy | None = None) -> S2RunResult:
    from .orchestrator import run_s2_pipeline
    return run_s2_pipeline(request=request, ports=ports or S2Ports(), policy=policy or S2Policy())
