from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .contracts.base import SearchStrategy, TrialPlanState, TrialState
from .contracts.budget import FidelityLevel
from .contracts.configuration import ConfigurationRecord
from .contracts.trials import (
    TrialExecutionPlan,
    TrialExecutionSlot,
    TrialResourceRequest,
    TrialSchedulingInput,
    TrialSchedulingOutcome,
    TrialSchedulingReport,
    TrialStateLedgerTemplate,
    TrialStateTemplateRecord,
)

TERMINAL_STATES = (
    TrialState.COMPLETED,
    TrialState.INVALID,
    TrialState.INFEASIBLE,
    TrialState.EARLY_STOPPED,
    TrialState.RESOURCE_EXHAUSTED,
    TrialState.FAILED,
    TrialState.QUARANTINED,
    TrialState.CANCELLED_UPSTREAM,
)


class HyperparameterTrialSchedulerAndStateReconciler:
    """Builds deterministic trial slots without executing any backtest."""

    def schedule(self, request: TrialSchedulingInput) -> TrialSchedulingOutcome:
        catalog = request.configuration_catalog
        if not catalog.configurations:
            return self._blocking(request, "P9_S2_TRIAL_NO_CONFIGURATIONS")
        if "cpu" not in request.worker_capabilities.worker_labels:
            return self._blocking(request, "P9_S2_TRIAL_WORKER_LABEL_UNAVAILABLE")
        if (
            request.budget_plan.memory_mb_per_trial
            > request.worker_capabilities.max_memory_mb_per_trial
        ):
            return self._blocking(request, "P9_S2_TRIAL_RESOURCE_UNAVAILABLE")
        if (
            request.budget_plan.parallel_trial_limit
            > request.worker_capabilities.max_parallel_trials
        ):
            return self._blocking(request, "P9_S2_TRIAL_PARALLELISM_UNAVAILABLE")

        cells = self._evaluation_cells(request)
        seeds = self._seeds(request)
        configurations = catalog.configurations
        strategy = request.budget_plan.search_strategy
        fidelities = request.budget_plan.fidelity_levels
        reduction_factor = 3

        selected_count = self._largest_schedulable_configuration_count(
            configurations=configurations,
            strategy=strategy,
            fidelities=fidelities,
            cells=cells,
            seeds=seeds,
            execution_limit=request.budget_plan.trial_execution_limit,
            reduction_factor=reduction_factor,
        )
        if selected_count < 1:
            return self._blocking(request, "P9_S2_TRIAL_BUDGET_INSUFFICIENT")
        selected = configurations[:selected_count]
        slots = self._build_slots(
            configurations=selected,
            strategy=strategy,
            fidelities=fidelities,
            cells=cells,
            seeds=seeds,
            reduction_factor=reduction_factor,
            request=request,
        )
        if len(slots) > request.budget_plan.trial_execution_limit:
            return self._blocking(request, "P9_S2_TRIAL_BUDGET_RECONCILIATION_FAILED")

        limitations: list[str] = []
        state = TrialPlanState.PLAN_READY
        if selected_count < len(configurations):
            state = TrialPlanState.PLAN_READY_LIMITED
            limitations.append("configuration catalog truncated to fit trial execution budget")
        if request.budget_plan.state.value == "BUDGET_LIMITED":
            state = TrialPlanState.PLAN_READY_LIMITED
            limitations.extend(request.budget_plan.limitations)

        plan_preimage = {
            "experiment_id": request.validated_specification.specification.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "budget_plan_sha256": request.budget_plan.plan_sha256,
            "catalog_sha256": request.configuration_catalog.catalog_sha256,
            "strategy": strategy,
            "temporal_evaluation": (
                request.validated_specification.specification.temporal_evaluation
            ),
            "slots": slots,
            "scheduler_policy_sha256": request.scheduler_policy.policy_sha256,
            "worker_capability_sha256": request.worker_capabilities.snapshot_sha256,
        }
        plan_hash = payload_sha256(plan_preimage)
        plan = TrialExecutionPlan(
            plan_id=f"trial-plan-{plan_hash}",
            experiment_id=request.validated_specification.specification.experiment_id,
            state=state,
            temporal_evaluation_request=(
                request.validated_specification.specification.temporal_evaluation
            ),
            slots=slots,
            plan_sha256=plan_hash,
            limitations=tuple(dict.fromkeys(limitations)),
        )
        ledger_records = tuple(
            TrialStateTemplateRecord(
                trial_id=slot.trial_id,
                current_state=slot.initial_state,
            )
            for slot in slots
        )
        ledger_preimage = {
            "plan_id": plan.plan_id,
            "records": ledger_records,
            "terminal_states": TERMINAL_STATES,
        }
        ledger_hash = payload_sha256(ledger_preimage)
        ledger = TrialStateLedgerTemplate(
            ledger_id=f"trial-state-template-{ledger_hash}",
            plan_id=plan.plan_id,
            records=ledger_records,
            terminal_states=TERMINAL_STATES,
            ledger_sha256=ledger_hash,
        )
        return TrialSchedulingOutcome(
            trial_plan=plan,
            trial_state_ledger=ledger,
            report=TrialSchedulingReport(
                state=state,
                limitations=tuple(dict.fromkeys(limitations)),
            ),
        )

    def _largest_schedulable_configuration_count(
        self,
        *,
        configurations: Sequence[ConfigurationRecord],
        strategy: SearchStrategy,
        fidelities: tuple[FidelityLevel, ...],
        cells: tuple[str, ...],
        seeds: tuple[int, ...],
        execution_limit: int,
        reduction_factor: int,
    ) -> int:
        multiplier = len(cells) * len(seeds)
        for count in range(len(configurations), 0, -1):
            groups = self._evaluation_group_count(
                count,
                strategy,
                len(fidelities),
                reduction_factor,
            )
            if groups * multiplier <= execution_limit:
                return count
        return 0

    @staticmethod
    def _evaluation_group_count(
        configuration_count: int,
        strategy: SearchStrategy,
        fidelity_count: int,
        reduction_factor: int,
    ) -> int:
        if strategy in {SearchStrategy.GRID, SearchStrategy.RANDOM}:
            return configuration_count
        if strategy is SearchStrategy.SUCCESSIVE_HALVING:
            total = configuration_count
            current = configuration_count
            for _ in range(1, fidelity_count):
                current = max(1, math.floor(current / reduction_factor))
                total += current
            return total
        if strategy is SearchStrategy.HYPERBAND:
            allocations = HyperparameterTrialSchedulerAndStateReconciler._hyperband_allocations(
                configuration_count,
                fidelity_count,
                reduction_factor,
            )
            total = 0
            for bracket_index, bracket_count in enumerate(allocations):
                level_count = fidelity_count - bracket_index
                current = bracket_count
                total += current
                for _ in range(1, level_count):
                    current = max(1, math.floor(current / reduction_factor))
                    total += current
            return total
        return 0

    def _build_slots(
        self,
        *,
        configurations: Sequence[ConfigurationRecord],
        strategy: SearchStrategy,
        fidelities: tuple[FidelityLevel, ...],
        cells: tuple[str, ...],
        seeds: tuple[int, ...],
        reduction_factor: int,
        request: TrialSchedulingInput,
    ) -> tuple[TrialExecutionSlot, ...]:
        if strategy in {SearchStrategy.GRID, SearchStrategy.RANDOM}:
            return self._assigned_rung_slots(
                configurations=configurations,
                fidelity=fidelities[-1],
                bracket_id=None,
                rung=0,
                cells=cells,
                seeds=seeds,
                dependencies=(),
                request=request,
            )
        if strategy is SearchStrategy.SUCCESSIVE_HALVING:
            return self._successive_halving_slots(
                configurations=configurations,
                fidelities=fidelities,
                bracket_id="sh-bracket-00",
                cells=cells,
                seeds=seeds,
                reduction_factor=reduction_factor,
                request=request,
            )
        if strategy is SearchStrategy.HYPERBAND:
            allocations = self._hyperband_allocations(
                len(configurations),
                len(fidelities),
                reduction_factor,
            )
            offset = 0
            slots: list[TrialExecutionSlot] = []
            for bracket_index, allocation in enumerate(allocations):
                subset = configurations[offset : offset + allocation]
                offset += allocation
                if not subset:
                    continue
                bracket_fidelities = fidelities[bracket_index:]
                slots.extend(
                    self._successive_halving_slots(
                        configurations=subset,
                        fidelities=bracket_fidelities,
                        bracket_id=f"hb-bracket-{bracket_index:02d}",
                        cells=cells,
                        seeds=seeds,
                        reduction_factor=reduction_factor,
                        request=request,
                    )
                )
            return tuple(slots)
        raise ValueError(f"unsupported scheduling strategy: {strategy}")

    def _successive_halving_slots(
        self,
        *,
        configurations: Sequence[ConfigurationRecord],
        fidelities: tuple[FidelityLevel, ...],
        bracket_id: str,
        cells: tuple[str, ...],
        seeds: tuple[int, ...],
        reduction_factor: int,
        request: TrialSchedulingInput,
    ) -> tuple[TrialExecutionSlot, ...]:
        slots: list[TrialExecutionSlot] = []
        previous_trial_ids: tuple[str, ...] = ()
        current_count = len(configurations)
        base_slots = self._assigned_rung_slots(
            configurations=configurations,
            fidelity=fidelities[0],
            bracket_id=bracket_id,
            rung=0,
            cells=cells,
            seeds=seeds,
            dependencies=(),
            request=request,
        )
        slots.extend(base_slots)
        previous_trial_ids = tuple(slot.trial_id for slot in base_slots)
        for rung, fidelity in enumerate(fidelities[1:], start=1):
            current_count = max(1, math.floor(current_count / reduction_factor))
            rung_slots = self._reserved_rung_slots(
                selection_count=current_count,
                fidelity=fidelity,
                bracket_id=bracket_id,
                rung=rung,
                cells=cells,
                seeds=seeds,
                dependencies=previous_trial_ids,
                request=request,
            )
            slots.extend(rung_slots)
            previous_trial_ids = tuple(slot.trial_id for slot in rung_slots)
        return tuple(slots)

    def _assigned_rung_slots(
        self,
        *,
        configurations: Sequence[ConfigurationRecord],
        fidelity: FidelityLevel,
        bracket_id: str | None,
        rung: int,
        cells: tuple[str, ...],
        seeds: tuple[int, ...],
        dependencies: tuple[str, ...],
        request: TrialSchedulingInput,
    ) -> tuple[TrialExecutionSlot, ...]:
        slots = []
        for configuration in configurations:
            for cell in cells:
                for seed in seeds:
                    slots.append(
                        self._slot(
                            configuration_id=configuration.configuration_id,
                            stage="EXPLORATION" if rung == 0 else "CONFIRMATION",
                            cell=cell,
                            seed=seed,
                            fidelity=fidelity,
                            bracket_id=bracket_id,
                            rung=rung,
                            dependencies=dependencies,
                            adaptive_assignment_key=None,
                            selection_rank=None,
                            request=request,
                        )
                    )
        return tuple(slots)

    def _reserved_rung_slots(
        self,
        *,
        selection_count: int,
        fidelity: FidelityLevel,
        bracket_id: str,
        rung: int,
        cells: tuple[str, ...],
        seeds: tuple[int, ...],
        dependencies: tuple[str, ...],
        request: TrialSchedulingInput,
    ) -> tuple[TrialExecutionSlot, ...]:
        slots = []
        for rank in range(selection_count):
            assignment_key = f"{bracket_id}.rung-{rung:02d}.rank-{rank:04d}"
            for cell in cells:
                for seed in seeds:
                    slots.append(
                        self._slot(
                            configuration_id=None,
                            stage="PROMOTION",
                            cell=cell,
                            seed=seed,
                            fidelity=fidelity,
                            bracket_id=bracket_id,
                            rung=rung,
                            dependencies=dependencies,
                            adaptive_assignment_key=assignment_key,
                            selection_rank=rank,
                            request=request,
                        )
                    )
        return tuple(slots)

    @staticmethod
    def _slot(
        *,
        configuration_id: str | None,
        stage: str,
        cell: str,
        seed: int,
        fidelity: FidelityLevel,
        bracket_id: str | None,
        rung: int,
        dependencies: tuple[str, ...],
        adaptive_assignment_key: str | None,
        selection_rank: int | None,
        request: TrialSchedulingInput,
    ) -> TrialExecutionSlot:
        preimage = {
            "experiment_id": request.validated_specification.specification.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "budget_plan_sha256": request.budget_plan.plan_sha256,
            "configuration_id": configuration_id,
            "stage": stage,
            "cell": cell,
            "seed": seed,
            "fidelity_id": fidelity.fidelity_id,
            "bracket_id": bracket_id,
            "rung": rung,
            "dependencies": dependencies,
            "adaptive_assignment_key": adaptive_assignment_key,
            "selection_rank": selection_rank,
            "scheduler_policy_sha256": request.scheduler_policy.policy_sha256,
        }
        slot_hash = payload_sha256(preimage)
        cpu_seconds = max(
            1,
            math.ceil(
                request.budget_plan.cpu_seconds_per_full_cell
                * float(fidelity.resource_fraction)
            ),
        )
        return TrialExecutionSlot(
            trial_id=f"trial-{slot_hash}",
            configuration_id=configuration_id,
            stage=stage,
            evaluation_cell_id=cell,
            seed=seed,
            fidelity_id=fidelity.fidelity_id,
            bracket_id=bracket_id,
            rung=rung,
            depends_on_trial_ids=dependencies,
            resource_request=TrialResourceRequest(
                cpu_seconds=cpu_seconds,
                memory_mb=request.budget_plan.memory_mb_per_trial,
                worker_labels=("cpu",),
            ),
            initial_state=(
                TrialState.PLANNED if configuration_id is not None else TrialState.RESERVED
            ),
            allowed_terminal_states=TERMINAL_STATES,
            idempotency_key=slot_hash,
            adaptive_assignment_key=adaptive_assignment_key,
            selection_rank=selection_rank,
        )

    @staticmethod
    def _evaluation_cells(request: TrialSchedulingInput) -> tuple[str, ...]:
        temporal = request.validated_specification.specification.temporal_evaluation
        return tuple(
            f"outer-{outer:02d}.inner-{inner:02d}"
            for outer in range(temporal.outer_fold_count)
            for inner in range(temporal.inner_fold_count)
        )

    @staticmethod
    def _seeds(request: TrialSchedulingInput) -> tuple[int, ...]:
        values = []
        for index in range(request.budget_plan.seed_count):
            material = (
                f"{request.seed_policy.base_seed}:"
                f"{request.validated_specification.specification.experiment_id}:"
                f"{index}"
            ).encode("utf-8")
            values.append(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))
        return tuple(values)

    @staticmethod
    def _hyperband_allocations(
        configuration_count: int,
        fidelity_count: int,
        reduction_factor: int,
    ) -> tuple[int, ...]:
        s_max = fidelity_count - 1
        desired = [
            math.ceil((s_max + 1) / (s + 1) * reduction_factor**s)
            for s in range(s_max, -1, -1)
        ]
        total_desired = sum(desired)
        raw = [configuration_count * value / total_desired for value in desired]
        allocations = [math.floor(value) for value in raw]
        remaining = configuration_count - sum(allocations)
        order = sorted(
            range(len(raw)),
            key=lambda index: (raw[index] - allocations[index], -index),
            reverse=True,
        )
        for index in order[:remaining]:
            allocations[index] += 1
        return tuple(allocations)

    @staticmethod
    def _blocking(
        request: TrialSchedulingInput,
        reason: str,
    ) -> TrialSchedulingOutcome:
        return TrialSchedulingOutcome(
            trial_plan=None,
            trial_state_ledger=None,
            report=TrialSchedulingReport(
                state=TrialPlanState.SCHEDULER_INFEASIBLE,
                reason_codes=(reason,),
            ),
        )
