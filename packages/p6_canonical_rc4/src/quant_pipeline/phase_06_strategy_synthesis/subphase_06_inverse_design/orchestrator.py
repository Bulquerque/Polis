"""Solver portfolio orchestration and candidate materialization."""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import OriginMode, SolverStatus, TemplateId
from ..domain.identity import candidate_id
from ..domain.models import (
    CandidateGenerationTrace,
    ReplicationBasisInstrument,
    SolverResult,
    StrategyCandidate,
    StrategySynthesisProblem,
    TargetPayoffRecord,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id

ZERO = Decimal("0")
ACCEPTED_STATUSES = {
    SolverStatus.OPTIMAL,
    SolverStatus.FEASIBLE,
}


def materialize_solver_candidates(
    problems: tuple[StrategySynthesisProblem, ...],
    targets: tuple[TargetPayoffRecord, ...],
    basis: tuple[ReplicationBasisInstrument, ...],
    results: tuple[SolverResult, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[StrategyCandidate, ...],
    tuple[CandidateGenerationTrace, ...],
]:
    """Convert feasible solver outputs into canonical strategy candidates."""
    problem_by_id = {item.problem_id: item for item in problems}
    target_by_id = {item.target_payoff_id: item for item in targets}
    basis_by_id = {item.basis_id: item for item in basis}
    grouped = _group_results(results)
    candidates: list[StrategyCandidate] = []
    traces: list[CandidateGenerationTrace] = []
    seen: set[str] = set()
    for problem_id, values in sorted(grouped.items()):
        problem = problem_by_id[problem_id]
        target = target_by_id[problem.target_payoff_id]
        ordered = sorted(values, key=_result_order)
        limit = configuration.solver.maximum_solutions_per_target
        for result in ordered[:limit]:
            pair = _materialize_result(
                problem,
                target,
                result,
                basis_by_id,
                configuration,
            )
            if pair is None or pair[0].candidate_id in seen:
                continue
            seen.add(pair[0].candidate_id)
            candidates.append(pair[0])
            traces.append(pair[1])
    return tuple(candidates), tuple(traces)


def combine_candidate_universe(
    template_candidates: tuple[StrategyCandidate, ...],
    template_traces: tuple[CandidateGenerationTrace, ...],
    mutated_candidates: tuple[StrategyCandidate, ...],
    mutation_traces: tuple[CandidateGenerationTrace, ...],
    inverse_candidates: tuple[StrategyCandidate, ...],
    inverse_traces: tuple[CandidateGenerationTrace, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[StrategyCandidate, ...],
    tuple[CandidateGenerationTrace, ...],
]:
    """Merge origins without ranking and enforce the pre-dedup budget."""
    candidate_by_id: dict[str, StrategyCandidate] = {}
    all_candidates = (
        template_candidates
        + mutated_candidates
        + inverse_candidates
    )
    for candidate in all_candidates:
        candidate_by_id.setdefault(candidate.candidate_id, candidate)
        if len(candidate_by_id) >= configuration.budgets.max_candidates_before_dedup:
            break
    trace_by_id: dict[str, CandidateGenerationTrace] = {}
    all_traces = template_traces + mutation_traces + inverse_traces
    for trace in all_traces:
        if trace.candidate_id in candidate_by_id:
            trace_by_id.setdefault(trace.candidate_id, trace)
    candidates = tuple(
        candidate_by_id[key]
        for key in sorted(candidate_by_id)
    )
    traces = tuple(
        trace_by_id[key]
        for key in sorted(trace_by_id)
    )
    return candidates, traces


def _group_results(
    results: tuple[SolverResult, ...],
) -> dict[str, list[SolverResult]]:
    grouped: dict[str, list[SolverResult]] = {}
    for result in results:
        if result.status in ACCEPTED_STATUSES and result.quantities:
            grouped.setdefault(result.problem_id, []).append(result)
    return grouped


def _result_order(result: SolverResult):
    return (
        result.objective_value is None,
        result.objective_value or Decimal("Infinity"),
        result.method.value,
    )


def _materialize_result(
    problem: StrategySynthesisProblem,
    target: TargetPayoffRecord,
    result: SolverResult,
    basis_by_id: dict[str, ReplicationBasisInstrument],
    configuration: Phase6RunConfiguration,
) -> tuple[StrategyCandidate, CandidateGenerationTrace] | None:
    legs = _legs(result, basis_by_id, configuration)
    if not legs:
        return None
    identifier = candidate_id(
        underlying_id=problem.underlying_id,
        decision_time=target.decision_time.isoformat(),
        legs=legs,
        objective_family=target.objective_family.value,
        policy_version=configuration.solver.policy_version,
        horizon_days=target.horizon_days,
    )
    candidate = StrategyCandidate(
        candidate_id=identifier,
        candidate_version="2",
        underlying_id=problem.underlying_id,
        decision_time=target.decision_time,
        horizon_days=target.horizon_days,
        objective_family=target.objective_family,
        origin_mode=OriginMode.INVERSE_DESIGN,
        origin_template_id=TemplateId.INVERSE_DESIGN_FREE_FORM,
        legs=legs,
        strategy_scale=Decimal("1"),
        generation_run_id=configuration.run_id,
        lineage_id=stable_id(
            "inverse-lineage",
            result.solver_result_id,
            identifier,
        ),
    )
    trace = CandidateGenerationTrace(
        candidate_id=identifier,
        origin=OriginMode.INVERSE_DESIGN,
        origin_template_id=TemplateId.INVERSE_DESIGN_FREE_FORM,
        operators=(),
        parameters={
            "problem_id": problem.problem_id,
            "target_payoff_id": target.target_payoff_id,
        },
        solver_id=result.solver_name,
        solver_status=result.status.value,
        generation_stage="P6.S6",
    )
    return candidate, trace


def _legs(
    result: SolverResult,
    basis_by_id: dict[str, ReplicationBasisInstrument],
    configuration: Phase6RunConfiguration,
) -> tuple:
    legs = []
    sides: dict[str, set[str]] = {}
    for item in result.quantities:
        basis = basis_by_id.get(item.basis_id)
        if basis is None:
            return ()
        quantity = item.quantity.to_integral_value()
        if quantity <= ZERO:
            continue
        sides.setdefault(basis.instrument_id, set()).add(
            basis.leg.side.value
        )
        legs.append(basis.leg.model_copy(update={"quantity": quantity}))
    if any(len(values) > 1 for values in sides.values()):
        return ()
    if len(legs) > configuration.budgets.max_legs:
        return ()
    return tuple(legs)
