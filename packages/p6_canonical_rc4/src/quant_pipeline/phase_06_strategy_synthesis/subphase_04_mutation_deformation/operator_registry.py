"""Declarative mutation-operator registry."""

from ..domain.enums import MutationOperator
from ..domain.models import MutationOperatorDefinition
from ..foundation.configuration import Phase6RunConfiguration


def operator_registry(
    configuration: Phase6RunConfiguration,
) -> tuple[MutationOperatorDefinition, ...]:
    """Return the enabled operators with explicit contracts."""
    maximum = configuration.mutation.max_applications_per_candidate
    definitions = {
        MutationOperator.MOVE_STRIKE: MutationOperatorDefinition(
            operator=MutationOperator.MOVE_STRIKE,
            preconditions=(
                "OPTION_LEG_EXISTS",
                "ADJACENT_CONTRACT_EXISTS",
            ),
            postconditions=("CONTRACTS_POINT_IN_TIME_VALID",),
            risk_effect="LOCAL_PAYOFF_SHIFT",
            complexity_cost=1,
            maximum_applications=maximum,
        ),
        MutationOperator.CHANGE_QUANTITY: MutationOperatorDefinition(
            operator=MutationOperator.CHANGE_QUANTITY,
            preconditions=("QUANTITY_BELOW_LIMIT",),
            postconditions=("INTEGER_QUANTITIES",),
            risk_effect="SCALE_OR_ASYMMETRY_CHANGE",
            complexity_cost=1,
            maximum_applications=maximum,
        ),
        MutationOperator.ADD_UNDERLYING: MutationOperatorDefinition(
            operator=MutationOperator.ADD_UNDERLYING,
            preconditions=(
                "UNDERLYING_QUOTE_EXECUTABLE",
                "NO_EXISTING_OVERLAY",
            ),
            postconditions=("STATIC_INITIAL_OVERLAY_ONLY",),
            risk_effect="TAIL_SLOPE_CHANGE",
            complexity_cost=1,
            maximum_applications=1,
        ),
        MutationOperator.REMOVE_REDUNDANT_LEG: (
            MutationOperatorDefinition(
                operator=MutationOperator.REMOVE_REDUNDANT_LEG,
                preconditions=(
                    "DUPLICATE_OR_CANCELLING_LEGS_EXIST",
                ),
                postconditions=("NO_ZERO_QUANTITY_LEGS",),
                risk_effect=(
                    "ECONOMICALLY_EQUIVALENT_SIMPLIFICATION"
                ),
                complexity_cost=0,
                maximum_applications=1,
            )
        ),
    }
    return tuple(
        definitions[operator]
        for operator in configuration.mutation.enabled_operators
        if operator in definitions
    )
