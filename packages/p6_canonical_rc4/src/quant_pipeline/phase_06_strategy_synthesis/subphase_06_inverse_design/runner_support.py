"""P6.S6 module implementations."""

from __future__ import annotations

from typing import Iterable

from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.results import ModuleResult
from .basis import build_replication_basis
from .orchestrator import (
    combine_candidate_universe,
    materialize_solver_candidates,
)
from .solvers import (
    beam_results,
    continuous_results,
    evolutionary_results,
    integer_results,
    local_results,
    synthesis_problems,
)


def _artifact(
    records: Iterable[object],
    name,
    module_id,
    context,
    *,
    status=None,
):
    return build_artifact(
        artifact_type=name,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=tuple(records),
        status=status,
    )


def basis(inputs, context, configuration):
    module_id = "P6.S6.M01"
    records = _basis_records(inputs, configuration)
    problems = synthesis_problems(
        tuple(inputs["target_payoff_panel"].records),
        tuple(inputs["target_payoff_qualification_report"].records),
        records,
        configuration,
    )
    outputs = {
        "replication_basis_panel": _artifact(
            records,
            "replication_basis_panel",
            module_id,
            context,
        ),
        "strategy_synthesis_problem_panel": _artifact(
            problems,
            "strategy_synthesis_problem_panel",
            module_id,
            context,
        ),
    }
    return ModuleResult(module_id=module_id, outputs=outputs)


def continuous(inputs, context, configuration):
    module_id = "P6.S6.M02"
    records = continuous_results(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        configuration,
    )
    return _single_result(
        module_id,
        "continuous_solver_result_panel",
        records,
        context,
    )


def integer(inputs, context, configuration):
    module_id = "P6.S6.M03"
    records = integer_results(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        tuple(inputs["continuous_solver_result_panel"].records),
        configuration,
    )
    return _single_result(
        module_id,
        "mixed_integer_solver_result_panel",
        records,
        context,
    )


def beam(inputs, context, configuration):
    module_id = "P6.S6.M04"
    records = beam_results(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        configuration,
    )
    return _single_result(
        module_id,
        "beam_solver_result_panel",
        records,
        context,
    )


def local(inputs, context, configuration):
    module_id = "P6.S6.M05"
    seeds = (
        tuple(inputs["mixed_integer_solver_result_panel"].records)
        + tuple(inputs["beam_solver_result_panel"].records)
    )
    records = local_results(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        seeds,
        configuration,
    )
    return _single_result(
        module_id,
        "local_search_solver_result_panel",
        records,
        context,
    )


def evolutionary(inputs, context, configuration):
    module_id = "P6.S6.M06"
    records = evolutionary_results(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        configuration,
    )
    unavailable = records and all(
        item.status.value == "UNAVAILABLE"
        for item in records
    )
    status = ArtifactStatus.DEGRADED if unavailable else None
    artifact = _artifact(
        records,
        "evolutionary_solver_result_panel",
        module_id,
        context,
        status=status,
    )
    return ModuleResult(
        module_id=module_id,
        outputs={"evolutionary_solver_result_panel": artifact},
    )


def orchestrate(inputs, context, configuration):
    module_id = "P6.S6.M07"
    solver_results = _all_solver_results(inputs)
    inverse, inverse_traces = materialize_solver_candidates(
        tuple(inputs["strategy_synthesis_problem_panel"].records),
        tuple(inputs["target_payoff_panel"].records),
        tuple(inputs["replication_basis_panel"].records),
        solver_results,
        configuration,
    )
    candidates, traces = combine_candidate_universe(
        tuple(inputs["raw_strategy_candidate_panel"].records),
        tuple(inputs["strategy_generation_trace_panel"].records),
        tuple(inputs["mutated_strategy_candidate_panel"].records),
        tuple(inputs["mutation_generation_trace_panel"].records),
        inverse,
        inverse_traces,
        configuration,
    )
    outputs = _orchestration_outputs(
        solver_results,
        inverse,
        inverse_traces,
        candidates,
        traces,
        module_id,
        context,
    )
    return ModuleResult(module_id=module_id, outputs=outputs)


def _basis_records(inputs, configuration):
    if not configuration.operational_mode.inverse_design_enabled:
        return ()
    return build_replication_basis(
        tuple(inputs["target_payoff_panel"].records),
        tuple(inputs["target_payoff_qualification_report"].records),
        tuple(inputs["eligible_option_contract_panel"].records),
        tuple(inputs["eligible_option_quote_panel"].records),
        tuple(inputs["validated_underlying_panel"].records),
        configuration,
    )


def _single_result(module_id, name, records, context):
    artifact = _artifact(records, name, module_id, context)
    return ModuleResult(module_id=module_id, outputs={name: artifact})


def _all_solver_results(inputs):
    names = (
        "continuous_solver_result_panel",
        "mixed_integer_solver_result_panel",
        "beam_solver_result_panel",
        "local_search_solver_result_panel",
        "evolutionary_solver_result_panel",
    )
    return tuple(
        record
        for name in names
        for record in inputs[name].records
    )


def _orchestration_outputs(
    solver_results,
    inverse,
    inverse_traces,
    candidates,
    traces,
    module_id,
    context,
):
    values = {
        "solver_result_panel": solver_results,
        "inverse_strategy_candidate_panel": inverse,
        "inverse_generation_trace_panel": inverse_traces,
        "synthesized_strategy_candidate_panel": candidates,
        "synthesized_generation_trace_panel": traces,
    }
    return {
        name: _artifact(records, name, module_id, context)
        for name, records in values.items()
    }
