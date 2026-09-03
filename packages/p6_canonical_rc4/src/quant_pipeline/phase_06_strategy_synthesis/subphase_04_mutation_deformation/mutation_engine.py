"""Deterministic orchestration of bounded local mutations."""

from __future__ import annotations

from ..domain.enums import MutationOperator
from ..domain.models import (
    CandidateGenerationTrace,
    ExecutableQuote,
    MutationApplication,
    OptionContractReference,
    StrategyCandidate,
    UnderlyingObservation,
)
from ..foundation.configuration import Phase6RunConfiguration
from .mutation_materialization import MutatedPair, build_trace
from .mutation_operators import (
    ContractSlice,
    add_underlying,
    change_quantity,
    contract_slices,
    move_strikes,
    remove_redundant,
)


def mutate_candidates(
    candidates: tuple[StrategyCandidate, ...],
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[StrategyCandidate, ...],
    tuple[CandidateGenerationTrace, ...],
    tuple[MutationApplication, ...],
]:
    """Generate deterministic children without exceeding configured budgets."""
    quote_by_id = {item.contract_id: item for item in quotes}
    underlying_by_id = {item.underlying_id: item for item in underlyings}
    slices = contract_slices(contracts)
    children: list[StrategyCandidate] = []
    traces: list[CandidateGenerationTrace] = []
    applications: list[MutationApplication] = []
    seen = {item.candidate_id for item in candidates}

    for parent in sorted(candidates, key=lambda item: item.candidate_id):
        generated = _mutate_parent(
            parent,
            slices,
            quote_by_id,
            underlying_by_id,
            configuration,
        )
        limit = configuration.mutation.max_children_per_parent
        for child, application in generated[:limit]:
            if child.candidate_id in seen:
                continue
            seen.add(child.candidate_id)
            children.append(child)
            applications.append(application)
            traces.append(build_trace(parent, child, application))
            if len(children) >= configuration.budgets.max_mutations:
                return tuple(children), tuple(traces), tuple(applications)
    return tuple(children), tuple(traces), tuple(applications)


def _mutate_parent(
    parent: StrategyCandidate,
    slices: dict[ContractSlice, tuple[OptionContractReference, ...]],
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
    configuration: Phase6RunConfiguration,
) -> list[MutatedPair]:
    output: list[MutatedPair] = []
    for operator in configuration.mutation.enabled_operators:
        output.extend(
            _apply_operator(
                operator,
                parent,
                slices,
                quote_by_id,
                underlying_by_id,
                configuration,
            )
        )
    return output


def _apply_operator(
    operator: MutationOperator,
    parent: StrategyCandidate,
    slices: dict[ContractSlice, tuple[OptionContractReference, ...]],
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
    configuration: Phase6RunConfiguration,
) -> list[MutatedPair]:
    if operator is MutationOperator.MOVE_STRIKE:
        return move_strikes(parent, slices, quote_by_id, configuration)
    if operator is MutationOperator.CHANGE_QUANTITY:
        return _optional(change_quantity(parent, configuration))
    if operator is MutationOperator.ADD_UNDERLYING:
        return _optional(add_underlying(parent, underlying_by_id, configuration))
    if operator is MutationOperator.REMOVE_REDUNDANT_LEG:
        return _optional(remove_redundant(parent, configuration))
    return []


def _optional(item: MutatedPair | None) -> list[MutatedPair]:
    return [] if item is None else [item]
