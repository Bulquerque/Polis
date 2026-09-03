from __future__ import annotations

from collections.abc import Mapping

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .conditions import parameter_is_active, topological_parameter_order
from .contracts.base import ConditionOperator, ParameterKind, SearchSpaceState
from .contracts.parameters import HyperparameterDefinition, ParameterScalar
from .contracts.search_space import (
    ActivationCondition,
    CompiledParameterDomain,
    CompiledSearchSpace,
    SearchSpaceCardinalityReport,
    SearchSpaceCompilationInput,
    SearchSpaceCompilationOutcome,
    SearchSpaceConstraintEdge,
    SearchSpaceConstraintGraph,
)
from .sampling import finite_domain_values


class ConditionalSearchSpaceCompiler:
    """Compiles a typed conditional search space without materializing large grids."""

    def compile(self, request: SearchSpaceCompilationInput) -> SearchSpaceCompilationOutcome:
        definitions = {
            definition.parameter_id: definition
            for definition in request.parameter_snapshot.definitions
        }
        reasons: list[str] = []
        limitations: list[str] = []
        compiled_unordered: list[CompiledParameterDomain] = []

        for domain in request.declaration.domains:
            definition = definitions.get(domain.parameter_id)
            if definition is None:
                reasons.append("P9_S2_SPACE_PARAMETER_UNKNOWN")
                continue
            domain_reasons = self._validate_domain_against_definition(domain, definition)
            reasons.extend(domain_reasons)
            conditions = tuple(
                ActivationCondition(
                    parent_parameter_id=condition.parent_parameter_id,
                    operator=ConditionOperator(condition.operator),
                    values=condition.values,
                )
                for condition in definition.active_when
            ) + domain.active_when
            compiled_unordered.append(
                CompiledParameterDomain(
                    parameter_id=domain.parameter_id,
                    kind=domain.kind,
                    scale=domain.scale,
                    discrete_values=domain.discrete_values,
                    lower=domain.lower,
                    upper=domain.upper,
                    grid_points=domain.grid_points,
                    active_when=conditions,
                    topological_index=0,
                )
            )

        if reasons:
            return SearchSpaceCompilationOutcome(
                compiled_space=self._blocking_space(
                    request,
                    SearchSpaceState.SPACE_INVALID,
                    tuple(sorted(set(reasons))),
                )
            )

        parameter_ids = tuple(domain.parameter_id for domain in compiled_unordered)
        edges = tuple(
            SearchSpaceConstraintEdge(
                parent_parameter_id=condition.parent_parameter_id,
                child_parameter_id=domain.parameter_id,
            )
            for domain in compiled_unordered
            for condition in domain.active_when
        )
        try:
            order = topological_parameter_order(parameter_ids, edges)
        except ValueError:
            return SearchSpaceCompilationOutcome(
                compiled_space=self._blocking_space(
                    request,
                    SearchSpaceState.SPACE_INVALID,
                    ("P9_S2_SPACE_CONDITION_CYCLE",),
                )
            )

        by_id = {domain.parameter_id: domain for domain in compiled_unordered}
        compiled = tuple(
            by_id[parameter_id].model_copy(update={"topological_index": index})
            for index, parameter_id in enumerate(order)
        )
        impossible = self._impossible_parameters(compiled)
        boundary_only = tuple(
            domain.parameter_id
            for domain in compiled
            if domain.discrete_values and len(domain.discrete_values) == 1
        )
        finite = all(domain.is_finite() for domain in compiled)
        if (
            request.validated_specification.specification.search_strategy.value == "GRID"
            and not finite
        ):
            return SearchSpaceCompilationOutcome(
                compiled_space=self._blocking_space(
                    request,
                    SearchSpaceState.SPACE_INVALID,
                    ("P9_S2_SPACE_GRID_REQUIRES_FINITE_DOMAINS",),
                    parameters=compiled,
                    edges=edges,
                    order=order,
                )
            )
        upper_bound = self._upper_bound(compiled) if finite else None

        if (
            upper_bound is not None
            and upper_bound > request.declaration.maximum_allowed_upper_bound
        ):
            return SearchSpaceCompilationOutcome(
                compiled_space=self._blocking_space(
                    request,
                    SearchSpaceState.SPACE_EXPLOSIVE,
                    ("P9_S2_SPACE_CARDINALITY_EXCESSIVE",),
                    parameters=compiled,
                    edges=edges,
                    order=order,
                    upper_bound=upper_bound,
                )
            )

        exact_cardinality: int | None = None
        if finite and upper_bound is not None:
            if upper_bound <= request.declaration.maximum_exact_cardinality:
                exact_cardinality = self._exact_cardinality(compiled, order)
            else:
                limitations.append("exact cardinality omitted because the finite space is large")

        if impossible:
            limitations.append("one or more parameters can never become active")
        if boundary_only:
            limitations.append("one or more parameters have a single search value")
        if exact_cardinality == 0:
            state = SearchSpaceState.SPACE_EMPTY
            reasons.append("P9_S2_SPACE_EMPTY")
        elif limitations:
            state = SearchSpaceState.SPACE_COMPILED_WITH_WARNINGS
        else:
            state = SearchSpaceState.SPACE_COMPILED

        cardinality = SearchSpaceCardinalityReport(
            finite=finite,
            exact_cardinality=exact_cardinality,
            upper_bound=upper_bound,
            effective_dimension_count=len(compiled) - len(impossible) - len(boundary_only),
            conditional_parameter_count=sum(bool(domain.active_when) for domain in compiled),
            inactive_parameter_ids=impossible,
            boundary_only_parameter_ids=boundary_only,
        )
        preimage = {
            "experiment_id": request.validated_specification.specification.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "parameter_snapshot_sha256": request.parameter_snapshot.snapshot_sha256,
            "declaration": request.declaration,
            "parameters": compiled,
            "order": order,
            "edges": edges,
            "cardinality": cardinality,
        }
        space_hash = payload_sha256(preimage)
        space = CompiledSearchSpace(
            space_id=f"search-space-{space_hash}",
            experiment_id=request.validated_specification.specification.experiment_id,
            specification_sha256=request.validated_specification.specification_sha256,
            state=state,
            parameters=compiled,
            constraint_graph=SearchSpaceConstraintGraph(parameter_order=order, edges=edges),
            cardinality=cardinality,
            space_sha256=space_hash,
            reason_codes=tuple(sorted(set(reasons))),
            limitations=tuple(dict.fromkeys(limitations)),
        )
        return SearchSpaceCompilationOutcome(compiled_space=space)

    @staticmethod
    def _validate_domain_against_definition(
        domain,
        definition: HyperparameterDefinition,
    ) -> list[str]:
        reasons: list[str] = []
        if domain.kind is not definition.kind:
            reasons.append("P9_S2_SPACE_TYPE_MISMATCH")
            return reasons
        if domain.scale is not definition.scale:
            reasons.append("P9_S2_SPACE_SCALE_MISMATCH")
        if domain.discrete_values:
            for value in domain.discrete_values:
                if not ConditionalSearchSpaceCompiler._value_valid(value, definition):
                    reasons.append("P9_S2_SPACE_VALUE_OUTSIDE_SCHEMA")
                    break
        else:
            if definition.lower is None or definition.upper is None:
                reasons.append("P9_S2_SPACE_SCHEMA_BOUNDS_MISSING")
            elif domain.lower is None or domain.upper is None:
                reasons.append("P9_S2_SPACE_BOUND_MISSING")
            elif domain.lower < definition.lower or domain.upper > definition.upper:
                reasons.append("P9_S2_SPACE_BOUND_OUTSIDE_SCHEMA")
        return reasons

    @staticmethod
    def _value_valid(value: ParameterScalar, definition: HyperparameterDefinition) -> bool:
        if definition.kind is ParameterKind.BOOLEAN:
            return isinstance(value, bool)
        if definition.kind is ParameterKind.INTEGER:
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and definition.lower is not None
                and definition.upper is not None
                and definition.lower <= value <= definition.upper
            )
        if definition.kind is ParameterKind.FLOAT:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and definition.lower is not None
                and definition.upper is not None
                and definition.lower <= value <= definition.upper
            )
        return value in definition.choices

    @staticmethod
    def _possible_values(domain: CompiledParameterDomain) -> tuple[ParameterScalar, ...] | None:
        if domain.is_finite():
            return finite_domain_values(domain)
        return None

    def _impossible_parameters(
        self,
        domains: tuple[CompiledParameterDomain, ...],
    ) -> tuple[str, ...]:
        by_id = {domain.parameter_id: domain for domain in domains}
        impossible: list[str] = []
        for domain in domains:
            for condition in domain.active_when:
                parent = by_id.get(condition.parent_parameter_id)
                if parent is None:
                    impossible.append(domain.parameter_id)
                    break
                possible = self._possible_values(parent)
                if possible is None:
                    continue
                satisfiable = any(
                    parameter_is_active((condition,), {condition.parent_parameter_id: value})
                    for value in possible
                )
                if not satisfiable:
                    impossible.append(domain.parameter_id)
                    break
        return tuple(sorted(set(impossible)))

    @staticmethod
    def _upper_bound(domains: tuple[CompiledParameterDomain, ...]) -> int:
        total = 1
        for domain in domains:
            total *= len(finite_domain_values(domain))
        return total

    @staticmethod
    def _exact_cardinality(
        domains: tuple[CompiledParameterDomain, ...],
        order: tuple[str, ...],
    ) -> int:
        by_id = {domain.parameter_id: domain for domain in domains}

        def count(index: int, assignments: dict[str, ParameterScalar]) -> int:
            if index == len(order):
                return 1
            domain = by_id[order[index]]
            if not parameter_is_active(domain.active_when, assignments):
                return count(index + 1, assignments)
            subtotal = 0
            for value in finite_domain_values(domain):
                assignments[domain.parameter_id] = value
                subtotal += count(index + 1, assignments)
            assignments.pop(domain.parameter_id, None)
            return subtotal

        return count(0, {})

    @staticmethod
    def _blocking_space(
        request: SearchSpaceCompilationInput,
        state: SearchSpaceState,
        reasons: tuple[str, ...],
        *,
        parameters: tuple[CompiledParameterDomain, ...] = (),
        edges: tuple[SearchSpaceConstraintEdge, ...] = (),
        order: tuple[str, ...] = (),
        upper_bound: int | None = None,
    ) -> CompiledSearchSpace:
        cardinality = SearchSpaceCardinalityReport(
            finite=upper_bound is not None,
            exact_cardinality=0 if state is SearchSpaceState.SPACE_EMPTY else None,
            upper_bound=upper_bound,
            effective_dimension_count=len(parameters),
            conditional_parameter_count=sum(
                bool(parameter.active_when) for parameter in parameters
            ),
        )
        preimage = {
            "experiment_id": request.validated_specification.specification.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "declaration": request.declaration,
            "state": state,
            "reasons": reasons,
            "parameters": parameters,
            "order": order,
            "edges": edges,
            "cardinality": cardinality,
        }
        space_hash = payload_sha256(preimage)
        return CompiledSearchSpace(
            space_id=f"search-space-{space_hash}",
            experiment_id=request.validated_specification.specification.experiment_id,
            specification_sha256=request.validated_specification.specification_sha256,
            state=state,
            parameters=parameters,
            constraint_graph=SearchSpaceConstraintGraph(parameter_order=order, edges=edges),
            cardinality=cardinality,
            space_sha256=space_hash,
            reason_codes=reasons,
        )
