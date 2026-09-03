from __future__ import annotations

from datetime import datetime, timezone

from .contracts.canonicalization import canonical_sha256, verify_payload_hash
from .models.artifacts import S5ResultPayload
from .models.inputs import DecisionReadyRiskBundle
from .modules import baseline_optimizer, constraint_compiler, discrete_repair, mpc_publisher, objective_compiler, rebalance_policy, robust_optimizer


def execute_s5(bundle: DecisionReadyRiskBundle) -> S5ResultPayload:
    verify_payload_hash(bundle.payload, bundle.envelope.content_sha256)
    if bundle.envelope.available_at > bundle.envelope.decision_time:
        raise ValueError("input bundle was unavailable at decision time")
    policy = bundle.payload.policy_context
    policy_without_hash = policy.model_copy(update={"content_sha256": "0" * 64})
    if canonical_sha256(policy_without_hash) != policy.content_sha256:
        raise ValueError("policy content hash mismatch")
    if not policy.effective_from_cycle <= bundle.envelope.cycle_id:
        raise ValueError("policy is not effective for cycle")
    if policy.expires_after_cycle is not None and bundle.envelope.cycle_id > policy.expires_after_cycle:
        raise ValueError("policy expired")
    objective = objective_compiler.run_module(bundle.payload)
    constraints = constraint_compiler.run_module(bundle.payload)
    nominal, problem = baseline_optimizer.run_module(bundle.payload, objective, constraints)
    robust = robust_optimizer.run_module(bundle.payload, objective, constraints, nominal, problem.input_hash)
    discrete = discrete_repair.run_module(bundle.payload, nominal, problem)
    decision = rebalance_policy.run_module(bundle.payload, discrete, problem)
    plan = mpc_publisher.run_module(bundle.payload, discrete, decision, bundle.envelope.decision_time)
    return S5ResultPayload(
        compiled_objective=objective,
        compiled_constraints=constraints,
        nominal_solution=nominal,
        robust_shadow=robust,
        discrete_target=discrete,
        rebalance_decision=decision,
        mpc_plan=plan,
        module_receipts=(
            "P8.S5.M01:SEMANTICALLY_CONSUMED",
            "P8.S5.M02:SEMANTICALLY_CONSUMED",
            "P8.S5.M03:SEMANTICALLY_CONSUMED",
            "P8.S5.M04:SHADOW_ONLY",
            "P8.S5.M05:SEMANTICALLY_CONSUMED",
            "P8.S5.M06:SEMANTICALLY_CONSUMED",
            "P8.S5.M07:PUBLISHED",
        ),
    )
