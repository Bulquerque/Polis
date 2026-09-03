from __future__ import annotations

from ..models.feedback import (
    CategoricalChangeBounds,
    FeedbackPolicyTarget,
    NumericChangeBounds,
    RootCauseEvidence,
)


def bounds_are_compatible(cause: RootCauseEvidence, target: FeedbackPolicyTarget) -> bool:
    target_numeric = {item.parameter_name: item for item in target.numeric_bounds}
    target_categorical = {item.parameter_name: item for item in target.categorical_bounds}

    for proposed in cause.numeric_change_bounds:
        allowed = target_numeric.get(proposed.parameter_name)
        if allowed is None:
            return False
        if (
            allowed.minimum is not None
            and proposed.minimum is not None
            and proposed.minimum < allowed.minimum
        ):
            return False
        if (
            allowed.maximum is not None
            and proposed.maximum is not None
            and proposed.maximum > allowed.maximum
        ):
            return False
        if (
            allowed.maximum_absolute_delta is not None
            and proposed.maximum_absolute_delta is not None
            and proposed.maximum_absolute_delta > allowed.maximum_absolute_delta
        ):
            return False
    for proposed in cause.categorical_change_bounds:
        allowed = target_categorical.get(proposed.parameter_name)
        if allowed is None:
            return False
        if not set(proposed.allowed_values).issubset(allowed.allowed_values):
            return False
    return True
