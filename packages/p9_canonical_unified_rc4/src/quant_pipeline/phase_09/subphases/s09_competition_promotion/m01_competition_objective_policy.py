from __future__ import annotations

from .enums import ModuleStatus, PolicyCompileState
from .models.common import ModuleDiagnostics, ModuleResult, build_module_result
from .models.policy import CompetitionObjectivePolicy, CompetitionObjectiveSpec

MODULE_ID = "P9.S9.M01"


def build_competition_objective_policy(
    spec: CompetitionObjectiveSpec,
) -> ModuleResult[CompetitionObjectivePolicy]:
    """Compile a precommitted competition objective into deterministic policy order."""

    policy = CompetitionObjectivePolicy(
        policy_id=spec.policy_id,
        policy_version=spec.policy_version,
        compile_state=PolicyCompileState.POLICY_COMPILED,
        primary_score_id=spec.primary_score_id,
        primary_score_version=spec.primary_score_version,
        primary_direction=spec.primary_direction,
        hard_gates=tuple(sorted(spec.hard_gates, key=lambda item: item.gate_id)),
        soft_penalties=tuple(sorted(spec.soft_penalties, key=lambda item: item.metric_id)),
        tie_breakers=tuple(sorted(spec.tie_breakers, key=lambda item: item.priority)),
        frontier_axes=tuple(sorted(spec.frontier_axes, key=lambda item: item.metric_id)),
        minimum_effect_size=spec.minimum_effect_size,
        minimum_probability_of_superiority=spec.minimum_probability_of_superiority,
        maximum_pbo=spec.maximum_pbo,
        minimum_dsr=spec.minimum_dsr,
        maximum_complexity_increase_without_material_gain=(
            spec.maximum_complexity_increase_without_material_gain
        ),
        allowed_deployment_stages=tuple(sorted(spec.allowed_deployment_stages)),
        committed_at=spec.committed_at,
        evaluation_started_at=spec.evaluation_started_at,
    )
    return build_module_result(
        module_id=MODULE_ID,
        status=ModuleStatus.SUCCESS,
        output=policy,
        diagnostics=ModuleDiagnostics(
            counters=(
                ("hard_gate_count", len(policy.hard_gates)),
                ("soft_penalty_count", len(policy.soft_penalties)),
                ("tie_breaker_count", len(policy.tie_breakers)),
                ("frontier_axis_count", len(policy.frontier_axes)),
            ),
            trace=("objective policy compiled from a precommitted strict specification",),
        ),
    )
