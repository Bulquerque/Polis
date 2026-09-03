from __future__ import annotations

import math
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .contracts.base import BudgetState, SearchStrategy
from .contracts.budget import (
    BudgetAllocation,
    BudgetPlanningInput,
    BudgetPlanningOutcome,
    BudgetPlanningReport,
    BudgetReservationReceipt,
    ComplexityPenaltyPolicy,
    SearchBudgetPlan,
)


def _allocate_by_fraction(
    total: int,
    fractions: tuple[Decimal, Decimal, Decimal],
) -> tuple[int, int, int]:
    """Allocate an integer total by exact Decimal fractions using largest remainder."""
    if total < 0:
        raise ValueError("allocation total cannot be negative")
    raw = [Decimal(total) * fraction for fraction in fractions]
    base = [int(value // 1) for value in raw]
    remainder = total - sum(base)
    order = sorted(
        range(len(raw)),
        key=lambda index: (raw[index] - Decimal(base[index]), -index),
        reverse=True,
    )
    for index in order[:remainder]:
        base[index] += 1
    positive = [index for index, value in enumerate(fractions) if value > 0]
    if total >= len(positive):
        for index in positive:
            if base[index] == 0:
                donor = max(
                    (candidate for candidate in range(len(base)) if base[candidate] > 1),
                    key=lambda candidate: base[candidate],
                    default=None,
                )
                if donor is not None:
                    base[donor] -= 1
                    base[index] += 1
    if sum(base) != total:
        raise RuntimeError("fractional allocation does not conserve total")
    return tuple(base)  # type: ignore[return-value]


class SearchBudgetAndComplexityController:
    """Reserves an auditable budget without using evaluation or holdout outcomes."""

    def plan(self, request: BudgetPlanningInput) -> BudgetPlanningOutcome:
        spec = request.validated_specification.specification
        reasons: list[str] = []
        limitations: list[str] = []

        if spec.search_strategy is SearchStrategy.BOHB:
            reasons.append("P9_S2_BUDGET_BOHB_CAPABILITY_UNAVAILABLE")
            return self._blocking(request, BudgetState.RESOURCE_CAPABILITY_UNAVAILABLE, reasons)

        fidelities = tuple(sorted(request.fidelity_levels, key=lambda level: level.ordinal))
        if fidelities[-1].resource_fraction != Decimal("1"):
            reasons.append("P9_S2_FIDELITY_FULL_LEVEL_MISSING")
        multi_fidelity = spec.search_strategy in {
            SearchStrategy.SUCCESSIVE_HALVING,
            SearchStrategy.HYPERBAND,
        }
        if multi_fidelity:
            if len(fidelities) < 2:
                reasons.append("P9_S2_FIDELITY_LEVELS_INSUFFICIENT")
            if not request.early_stopping.enabled:
                reasons.append("P9_S2_EARLY_STOP_REQUIRED")
        elif len(fidelities) > 1:
            fidelities = (fidelities[-1],)
            limitations.append("non-bandit strategy uses only the full-fidelity level")

        for fidelity in fidelities:
            if not (
                fidelity.preserves_transaction_costs
                and fidelity.preserves_lifecycle
                and fidelity.preserves_temporal_order
            ):
                reasons.append("P9_S2_FIDELITY_ECONOMICALLY_INVALID")
                break

        allowed_signals = {
            spec.primary_metric_id,
            *spec.hard_guardrail_metric_ids,
            *spec.diagnostic_metric_ids,
        }
        if not set(request.early_stopping.signal_metric_ids) <= allowed_signals:
            reasons.append("P9_S2_EARLY_STOP_INVALID_SIGNAL")

        if reasons:
            return self._blocking(request, BudgetState.BUDGET_INFEASIBLE, reasons)

        evaluation_cells = (
            spec.temporal_evaluation.outer_fold_count
            * spec.temporal_evaluation.inner_fold_count
        )
        seed_count = spec.requested_seed_count
        policy = request.budget_policy
        capacity = request.resource_capacity
        cpu_cap = min(policy.maximum_total_cpu_seconds, capacity.max_total_cpu_seconds)
        parallel_cap = min(
            policy.maximum_parallel_trials,
            capacity.max_parallel_trials,
        )
        memory_ok = policy.estimated_memory_mb_per_trial <= capacity.max_memory_mb_per_trial
        if not memory_ok:
            reasons.append("P9_S2_BUDGET_MEMORY_CAPACITY_EXCEEDED")
            return self._blocking(request, BudgetState.BUDGET_INFEASIBLE, reasons)

        full_cost_per_execution = policy.estimated_cpu_seconds_per_cell
        maximum_executions_by_cpu = cpu_cap // full_cost_per_execution
        maximum_executions_by_wall = (
            capacity.max_wall_clock_seconds * parallel_cap
        ) // full_cost_per_execution
        execution_limit = min(
            policy.maximum_trial_executions,
            maximum_executions_by_cpu,
            maximum_executions_by_wall,
        )
        cells_per_configuration = evaluation_cells * seed_count
        configuration_limit_by_execution = execution_limit // cells_per_configuration
        cardinality_limit = request.compiled_search_space.cardinality.exact_cardinality
        requested_limit = min(
            spec.requested_max_configurations,
            policy.maximum_configurations,
        )
        if cardinality_limit is not None:
            requested_limit = min(requested_limit, cardinality_limit)
        configuration_limit = min(requested_limit, configuration_limit_by_execution)

        if configuration_limit < 1 or execution_limit < cells_per_configuration:
            reasons.append("P9_S2_BUDGET_EXCEEDS_CAPACITY")
            return self._blocking(request, BudgetState.BUDGET_INFEASIBLE, reasons)

        resource_limited = False
        if configuration_limit < spec.requested_max_configurations:
            limitations.append("configuration count reduced by resource or policy budget")
            resource_limited = True
        if parallel_cap < policy.maximum_parallel_trials:
            limitations.append("parallelism reduced by available worker capacity")
            resource_limited = True
        if maximum_executions_by_cpu < policy.maximum_trial_executions:
            limitations.append("trial executions reduced by total CPU capacity")
            resource_limited = True
        if maximum_executions_by_wall < policy.maximum_trial_executions:
            limitations.append("trial executions reduced by wall-clock capacity")
            resource_limited = True
        if resource_limited and not policy.allow_resource_limited_plan:
            reasons.append("P9_S2_RESOURCE_LIMITED_PLAN_DISALLOWED")
            return self._blocking(request, BudgetState.BUDGET_INFEASIBLE, reasons)

        fractions = (
            policy.exploration_fraction,
            policy.confirmation_fraction,
            policy.robustness_fraction,
        )
        config_allocations = _allocate_by_fraction(configuration_limit, fractions)
        execution_allocations = _allocate_by_fraction(execution_limit, fractions)
        stages = ("EXPLORATION", "CONFIRMATION", "ROBUSTNESS")
        allocations = tuple(
            BudgetAllocation(
                stage=stage,
                configuration_slots=config_slots,
                trial_execution_slots=execution_slots,
                cpu_seconds_reserved=execution_slots * full_cost_per_execution,
            )
            for stage, config_slots, execution_slots in zip(
                stages,
                config_allocations,
                execution_allocations,
                strict=True,
            )
        )
        adaptive_depth = len(fidelities) - 1 if multi_fidelity else 0
        penalty_preimage = {
            "effective_dimension_count": (
                request.compiled_search_space.cardinality.effective_dimension_count
            ),
            "nominal_configuration_count": (
                request.compiled_search_space.cardinality.upper_bound
            ),
            "adaptive_search_depth": adaptive_depth,
            "search_strategy": spec.search_strategy,
        }
        penalty_hash = payload_sha256(penalty_preimage)
        penalty = ComplexityPenaltyPolicy(
            policy_id=f"complexity-{penalty_hash}",
            effective_dimension_count=(
                request.compiled_search_space.cardinality.effective_dimension_count
            ),
            nominal_configuration_count=(
                request.compiled_search_space.cardinality.upper_bound
            ),
            adaptive_search_depth=adaptive_depth,
            penalty_metadata_sha256=penalty_hash,
        )
        state = BudgetState.BUDGET_LIMITED if limitations else BudgetState.BUDGET_RESERVED
        plan_preimage = {
            "experiment_id": spec.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "search_space_sha256": request.compiled_search_space.space_sha256,
            "strategy": spec.search_strategy,
            "configuration_limit": configuration_limit,
            "execution_limit": execution_limit,
            "parallel_cap": parallel_cap,
            "wall_clock_seconds_limit": capacity.max_wall_clock_seconds,
            "seed_count": seed_count,
            "evaluation_cells": evaluation_cells,
            "fidelities": fidelities,
            "allocations": allocations,
            "early_stopping": request.early_stopping,
            "complexity_penalty": penalty,
            "budget_policy_sha256": policy.policy_sha256,
            "capacity_sha256": capacity.snapshot_sha256,
        }
        plan_hash = payload_sha256(plan_preimage)
        plan = SearchBudgetPlan(
            plan_id=f"search-budget-{plan_hash}",
            experiment_id=spec.experiment_id,
            state=state,
            search_strategy=spec.search_strategy,
            configuration_limit=configuration_limit,
            trial_execution_limit=execution_limit,
            parallel_trial_limit=parallel_cap,
            seed_count=seed_count,
            evaluation_cell_count=evaluation_cells,
            cpu_seconds_per_full_cell=full_cost_per_execution,
            memory_mb_per_trial=policy.estimated_memory_mb_per_trial,
            wall_clock_seconds_limit=capacity.max_wall_clock_seconds,
            fidelity_levels=fidelities,
            allocations=allocations,
            early_stopping=request.early_stopping,
            complexity_penalty=penalty,
            plan_sha256=plan_hash,
            limitations=tuple(limitations),
        )
        reservation_preimage = {
            "plan_id": plan.plan_id,
            "capacity_snapshot_id": capacity.snapshot_id,
            "reserved_cpu_seconds": sum(
                allocation.cpu_seconds_reserved for allocation in allocations
            ),
            "reserved_parallel_trials": parallel_cap,
        }
        reservation_hash = payload_sha256(reservation_preimage)
        reservation = BudgetReservationReceipt(
            reservation_id=f"budget-reservation-{reservation_hash}",
            plan_id=plan.plan_id,
            capacity_snapshot_id=capacity.snapshot_id,
            reserved_cpu_seconds=sum(
                allocation.cpu_seconds_reserved for allocation in allocations
            ),
            reserved_parallel_trials=parallel_cap,
            reservation_sha256=reservation_hash,
        )
        return BudgetPlanningOutcome(
            budget_plan=plan,
            reservation_receipt=reservation,
            report=BudgetPlanningReport(
                state=state,
                limitations=tuple(limitations),
            ),
        )

    @staticmethod
    def _blocking(
        request: BudgetPlanningInput,
        state: BudgetState,
        reasons: list[str],
    ) -> BudgetPlanningOutcome:
        return BudgetPlanningOutcome(
            budget_plan=None,
            reservation_receipt=None,
            report=BudgetPlanningReport(
                state=state,
                reason_codes=tuple(sorted(set(reasons))),
            ),
        )
