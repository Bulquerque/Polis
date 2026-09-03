"""Stable orchestration API joining P8.S1 and P8.S2 through their public contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from quant_pipeline.phase_08_contracts.canonical import finalize_content_hash
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import (
    S1Ports,
    S1RunRequest,
    S1RunResult,
    run_s1,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import S1Policy
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import (
    S2Ports,
    S2RunRequest,
    S2RunResult,
    build_s2_input_bundle,
    run_s2,
)
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.context import S2ExecutionContext
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.contracts.bundle import S2InputBundleV1
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.policies import S2Policy

from .contracts import Agent1IntegrationReceiptV1


@dataclass(frozen=True, slots=True)
class Agent1RunRequest:
    s1_request: S1RunRequest
    s2_computed_at: datetime

    def __post_init__(self) -> None:
        if self.s2_computed_at.tzinfo is None or self.s2_computed_at.utcoffset() is None:
            raise ValueError("s2_computed_at must be timezone-aware")
        normalized = self.s2_computed_at.astimezone(UTC)
        object.__setattr__(self, "s2_computed_at", normalized)
        if normalized < self.s1_request.context.computed_at:
            raise ValueError("s2_computed_at must not be before S1 computed_at")


@dataclass(frozen=True, slots=True)
class Agent1Ports:
    s1: S1Ports
    s2: S2Ports = field(default_factory=S2Ports)


@dataclass(frozen=True, slots=True)
class Agent1Policy:
    s1: S1Policy = field(default_factory=S1Policy)
    s2: S2Policy = field(default_factory=S2Policy)


@dataclass(frozen=True, slots=True)
class Agent1RunResult:
    s1: S1RunResult
    s2_input: S2InputBundleV1
    s2: S2RunResult
    receipt: Agent1IntegrationReceiptV1


def run_agent1(
    request: Agent1RunRequest,
    ports: Agent1Ports,
    policy: Agent1Policy | None = None,
) -> Agent1RunResult:
    """Run S1 and S2 without bypassing either subphase's public API or contracts."""

    active_policy = policy or Agent1Policy()
    s1_result = run_s1(request.s1_request, ports.s1, active_policy.s1)
    s2_input = build_s2_input_bundle(
        validated_handoff=s1_result.m01.bundle,
        terminal_ledger=s1_result.m02.ledger,
        resolved_evidence=s1_result.m03.evidence_index,
        feedback_context=s1_result.m04.feedback_context,
        current_state=s1_result.m05.current_state,
        snapshot=s1_result.m06.snapshot,
    )
    snapshot = s1_result.snapshot
    s2_context = S2ExecutionContext(
        run_id=snapshot.run_id,
        cycle_id=snapshot.cycle_id,
        decision_time=snapshot.decision_time,
        computed_at=request.s2_computed_at,
    )
    s2_result = run_s2(
        S2RunRequest(input_bundle=s2_input, context=s2_context),
        ports=ports.s2,
        policy=active_policy.s2,
    )
    receipt = finalize_content_hash(Agent1IntegrationReceiptV1(
        contract_version="P8_AGENT1_INTEGRATION_RECEIPT_V1",
        schema_version="1.0.0",
        integration_release="0.1.0",
        run_id=snapshot.run_id,
        cycle_id=snapshot.cycle_id,
        s1_snapshot_id=snapshot.snapshot_id,
        s1_snapshot_hash=snapshot.content_sha256,
        s2_input_hash=s2_input.content_sha256,
        s2_output_hash=s2_result.bundle.content_sha256,
        received_candidate_count=s1_result.m02.ledger.proof.received_count,
        actionable_candidate_count=len(snapshot.actionable_ranked_candidate_ids),
        forwarded_candidate_count=len(s2_result.bundle.static_action_universe.forwarded_candidate_ids),
        no_action_valid=snapshot.no_action is not None,
        content_sha256="0" * 64,
    ))
    return Agent1RunResult(s1=s1_result, s2_input=s2_input, s2=s2_result, receipt=receipt)
