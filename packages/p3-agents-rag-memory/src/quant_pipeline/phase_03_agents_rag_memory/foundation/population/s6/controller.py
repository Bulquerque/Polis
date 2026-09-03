"""P3.S6.M02 explicit NOVELTY -> DENSITY -> FINALIZED state machine."""
from __future__ import annotations
from .errors import ContractError, InvalidTransitionError
from .hashing import sha256_hex, stable_short_id
from .models import (
    ControlAction, CoverageControlRequest, CoverageControlResult,
    FinalizedPersonalityCandidatePool, GenerationMode, GenerationStatus,
    PopulationGenerationControl, PopulationGenerationStateV3,
)

class CoverageDensityController:
    """Decide the next generation action without generating or mutating candidates."""

    module_id = "P3.S6.M02"

    def execute(self, request: CoverageControlRequest) -> CoverageControlResult:
        report = request.personality_coverage_report
        accumulator = request.population_candidate_accumulator
        config = request.coverage_density_config
        if report.accumulator_hash != accumulator.accumulator_hash:
            raise ContractError("P3_S6_M02_ACCUMULATOR_HASH_MISMATCH")
        if report.generation_round != accumulator.current_round:
            raise ContractError("P3_S6_M02_ROUND_MISMATCH")
        if report.config_hash != sha256_hex(config.model_dump(mode="json")):
            raise ContractError("P3_S6_M02_CONFIG_HASH_MISMATCH")
        decision = self._decide(request)
        control = self._build_control(request, *decision)
        if control.materialize_finalized_pool:
            finalized = self._finalized_pool(request)
            return CoverageControlResult(
                population_generation_control=control,
                finalized_personality_candidate_pool=finalized,
            )
        next_state = self._next_state(request, control)
        return CoverageControlResult(
            population_generation_control=control,
            next_population_generation_state=next_state,
        )

    def _decide(self, request):
        report = request.personality_coverage_report
        config = request.coverage_density_config
        completed_rounds = report.generation_round + 1
        at_max = completed_rounds >= config.max_generation_rounds
        criteria_met = self._criteria_met(request)
        if report.mode is GenerationMode.NOVELTY:
            if at_max:
                return self._max_round_decision(request)
            if completed_rounds < config.minimum_novelty_rounds:
                return (
                    GenerationStatus.CONTINUE,
                    ControlAction.GENERATE_NOVELTY,
                    GenerationMode.NOVELTY,
                    0 if report.coverage.marginal_coverage_gain > config.coverage_epsilon else report.prior_patience_counter + 1,
                    None,
                )
            patience = (
                0
                if report.coverage.marginal_coverage_gain > config.coverage_epsilon
                else report.prior_patience_counter + 1
            )
            if patience >= config.patience_rounds or criteria_met:
                return (
                    GenerationStatus.TRANSITION_TO_DENSITY,
                    ControlAction.GENERATE_DENSITY,
                    GenerationMode.DENSITY,
                    0,
                    "NOVELTY_PATIENCE_REACHED" if not criteria_met else "COVERAGE_READY_FOR_DENSITY_CONFIRMATION",
                )
            return (
                GenerationStatus.CONTINUE,
                ControlAction.GENERATE_NOVELTY,
                GenerationMode.NOVELTY,
                patience,
                None,
            )
        if report.mode is GenerationMode.DENSITY:
            if criteria_met:
                return (
                    GenerationStatus.FINALIZED_VALID,
                    ControlAction.FINALIZE,
                    None,
                    report.prior_patience_counter,
                    "ALL_FINALIZATION_CRITERIA_MET",
                )
            if at_max:
                return self._max_round_decision(request)
            return (
                GenerationStatus.CONTINUE,
                ControlAction.GENERATE_DENSITY,
                GenerationMode.DENSITY,
                report.prior_patience_counter,
                None,
            )
        raise InvalidTransitionError("P3_S6_M02_UNKNOWN_MODE")

    def _criteria_met(self, request):
        report = request.personality_coverage_report
        config = request.coverage_density_config
        return (
            report.candidate_count >= config.target_population_size
            and report.coverage.overall_coverage_ratio >= config.minimum_coverage_ratio
            and report.coverage.tag_coverage_ratio >= config.minimum_tag_coverage_ratio
            and report.coverage.role_coverage_ratio >= config.minimum_role_coverage_ratio
            and report.density_sufficiency_ratio >= config.minimum_density_sufficiency_ratio
        )

    def _max_round_decision(self, request):
        report = request.personality_coverage_report
        config = request.coverage_density_config
        if report.coverage.overall_coverage_ratio >= config.degraded_minimum_coverage_ratio:
            return (
                GenerationStatus.DEGRADED_MAX_ROUNDS,
                ControlAction.STOP_DEGRADED,
                None,
                report.prior_patience_counter,
                "MAX_GENERATION_ROUNDS_REACHED_WITH_PARTIAL_COVERAGE",
            )
        return (
            GenerationStatus.FAILED_MAX_ROUNDS,
            ControlAction.STOP_FAILED,
            None,
            report.prior_patience_counter,
            "MAX_GENERATION_ROUNDS_REACHED_WITH_INSUFFICIENT_COVERAGE",
        )

    def _build_control(self, request, status, action, next_mode, patience, reason):
        report = request.personality_coverage_report
        materialize_final = status is GenerationStatus.FINALIZED_VALID
        payload = {
            "creator_run_id": report.creator_run_id,
            "generation_round": report.generation_round,
            "current_mode": report.mode,
            "next_mode": next_mode,
            "status": status,
            "action": action,
            "reason": reason,
            "patience": patience,
            "missing": report.coverage.missing_cell_ids,
        }
        control_hash = sha256_hex(payload)
        return PopulationGenerationControl(
            creator_run_id=report.creator_run_id,
            generation_round=report.generation_round,
            current_mode=report.mode,
            next_mode=next_mode,
            status=status,
            action=action,
            stop_reason=reason,
            patience_counter=patience,
            required_missing_cell_ids=report.coverage.missing_cell_ids,
            materialize_next_state=not materialize_final,
            materialize_finalized_pool=materialize_final,
            control_hash=control_hash,
            lineage_id=stable_short_id("lin", {"module": self.module_id, "control": control_hash}),
        )

    def _next_state(self, request, control):
        report = request.personality_coverage_report
        accumulator = request.population_candidate_accumulator
        next_mode = control.next_mode or report.mode
        density_targets = tuple(
            metric.candidate_id for metric in report.candidate_metrics if not metric.density_sufficient
        )
        payload = {
            "creator_run_id": report.creator_run_id,
            "generation_round": report.generation_round,
            "mode": next_mode,
            "candidate_ids": [record.candidate.candidate_id for record in accumulator.records],
            "covered": [cell.cell_id for cell in report.cells if cell.covered],
            "missing": report.coverage.missing_cell_ids,
            "density_targets": density_targets,
            "patience": control.patience_counter,
            "coverage": report.coverage.overall_coverage_ratio,
            "terminal": control.status if control.status in {
                GenerationStatus.DEGRADED_MAX_ROUNDS,
                GenerationStatus.FAILED_MAX_ROUNDS,
            } else None,
            "accumulator_hash": accumulator.accumulator_hash,
        }
        state_hash = sha256_hex(payload)
        return PopulationGenerationStateV3(
            creator_run_id=report.creator_run_id,
            generation_round=report.generation_round,
            mode=next_mode,
            accepted_candidate_ids=tuple(
                record.candidate.candidate_id for record in accumulator.records
            ),
            covered_cell_ids=tuple(cell.cell_id for cell in report.cells if cell.covered),
            missing_coverage_cells=report.coverage.missing_cell_ids,
            density_targets=density_targets,
            patience_counter=control.patience_counter,
            previous_coverage_ratio=report.coverage.overall_coverage_ratio,
            accumulator=accumulator,
            terminal_status=(
                control.status
                if control.status in {GenerationStatus.DEGRADED_MAX_ROUNDS, GenerationStatus.FAILED_MAX_ROUNDS}
                else None
            ),
            state_hash=state_hash,
            lineage_id=stable_short_id("lin", {"module": self.module_id, "state": state_hash}),
        )

    def _finalized_pool(self, request):
        report = request.personality_coverage_report
        accumulator = request.population_candidate_accumulator
        candidates = tuple(record.candidate for record in accumulator.records)
        pool_hash = sha256_hex([candidate.model_dump(mode="json") for candidate in candidates])
        return FinalizedPersonalityCandidatePool(
            creator_run_id=report.creator_run_id,
            final_generation_round=report.generation_round,
            candidates=candidates,
            coverage_report_hash=report.report_hash,
            accumulator_hash=accumulator.accumulator_hash,
            pool_hash=pool_hash,
            lineage_id=stable_short_id("lin", {"module": self.module_id, "pool": pool_hash}),
        )
