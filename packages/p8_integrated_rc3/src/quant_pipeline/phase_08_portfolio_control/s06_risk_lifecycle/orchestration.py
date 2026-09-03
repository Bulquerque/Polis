from __future__ import annotations

from datetime import datetime

from quant_pipeline.phase_08_portfolio_control.s05_optimization.contracts.canonicalization import (
    canonical_sha256,
    verify_payload_hash,
)
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.artifacts import S5ResultBundle
from quant_pipeline.phase_08_portfolio_control.s05_optimization.models.inputs import DecisionReadyRiskBundle

from .errors import ContractIntegrityError, PolicyIntegrityError, TemporalIntegrityError
from .models.artifacts import ExecutionAuthorizationPayload
from .models.inputs import RiskLifecycleContextBundle
from .models.policies import ApprovedS6PolicyContext
from .modules import emergency_planner, finalizer, hedge_planner, lifecycle_engine, risk_gate


def _verify_hashes(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
) -> None:
    verify_payload_hash(risk_bundle.payload, risk_bundle.envelope.content_sha256)
    verify_payload_hash(s5_bundle.payload, s5_bundle.envelope.content_sha256)
    verify_payload_hash(context.payload, context.envelope.content_sha256)


def _verify_identity(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
) -> None:
    expected_snapshot = risk_bundle.payload.decision_snapshot_hash
    snapshots = {
        expected_snapshot,
        s5_bundle.payload.mpc_plan.decision_snapshot_hash,
        context.payload.decision_snapshot_hash,
    }
    if len(snapshots) != 1:
        raise ContractIntegrityError("decision snapshot hash mismatch")
    if len({risk_bundle.envelope.run_id, s5_bundle.envelope.run_id, context.envelope.run_id}) != 1:
        raise ContractIntegrityError("run ID mismatch")
    if len({risk_bundle.envelope.cycle_id, s5_bundle.envelope.cycle_id, context.envelope.cycle_id}) != 1:
        raise ContractIntegrityError("cycle ID mismatch")


def _verify_temporal_integrity(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
) -> None:
    decision_time = risk_bundle.envelope.decision_time
    if any(item.envelope.decision_time != decision_time for item in (s5_bundle, context)):
        raise TemporalIntegrityError("decision time mismatch")
    if any(item.envelope.available_at > decision_time for item in (risk_bundle, context)):
        raise TemporalIntegrityError("input unavailable at decision time")


def _verify_policy(policy: ApprovedS6PolicyContext, cycle_id: str) -> None:
    draft = policy.model_copy(update={"content_sha256": "0" * 64})
    if canonical_sha256(draft) != policy.content_sha256:
        raise PolicyIntegrityError("policy content hash mismatch")
    if cycle_id < policy.effective_from_cycle:
        raise PolicyIntegrityError("policy not effective for cycle")
    if policy.expires_after_cycle is not None and cycle_id > policy.expires_after_cycle:
        raise PolicyIntegrityError("policy not effective for cycle")


def _verify_inputs(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
) -> None:
    _verify_hashes(risk_bundle, s5_bundle, context)
    _verify_identity(risk_bundle, s5_bundle, context)
    _verify_temporal_integrity(risk_bundle, s5_bundle, context)
    _verify_policy(context.payload.policy_context, context.envelope.cycle_id)


def execute_s6(
    risk_bundle: DecisionReadyRiskBundle,
    s5_bundle: S5ResultBundle,
    context: RiskLifecycleContextBundle,
    *,
    processing_time: datetime,
) -> ExecutionAuthorizationPayload:
    _verify_inputs(risk_bundle, s5_bundle, context)
    policy = context.payload.policy_context
    gate = risk_gate.run_module(risk_bundle, s5_bundle, policy.risk_gate)
    hedge = hedge_planner.run_module(
        risk_bundle, s5_bundle, gate, policy.hedge, policy.risk_gate
    )
    lifecycle = lifecycle_engine.run_module(
        risk_bundle,
        s5_bundle,
        context.payload.lifecycle_candidates,
        policy.lifecycle,
        processing_time,
    )
    emergency = emergency_planner.run_module(
        risk_bundle, s5_bundle, context.payload.emergency_state, policy.emergency
    )
    return finalizer.run_module(
        s5_bundle,
        gate,
        hedge,
        lifecycle,
        emergency,
        policy.authorization,
        processing_time,
    )
