from __future__ import annotations

import itertools
import math

import numpy as np

from .contracts import BreachDirection, S6State
from .models import (
    ConstraintCliff,
    FactorSensitivity,
    InteractionSensitivity,
    SensitivitySurfaceRequest,
    SensitivitySurfaceResult,
    SurfacePoint,
)
from .numerics import evaluate_quadratic_response, is_breached


def _complete_vector(request: SensitivitySurfaceRequest, partial: dict[str, float]) -> list[float]:
    return [partial.get(factor_id, 0.0) for factor_id in request.response_model.factor_ids]


def _point_constraints(request: SensitivitySurfaceRequest, value: float) -> tuple[str, ...]:
    return tuple(
        constraint.constraint_id
        for constraint in request.constraints
        if is_breached(value, constraint.threshold, constraint.breach_direction)
    )


def _is_extrapolated(request: SensitivitySurfaceRequest, partial: dict[str, float]) -> bool:
    axes = {axis.factor_id: axis for axis in request.axes}
    for factor_id, value in partial.items():
        axis = axes[factor_id]
        if axis.observed_min is None:
            continue
        if value < axis.observed_min - request.policy.extrapolation_margin:
            return True
        if value > axis.observed_max + request.policy.extrapolation_margin:
            return True
    return False


def _detect_cliffs(
    request: SensitivitySurfaceRequest,
    points: tuple[SurfacePoint, ...],
) -> tuple[ConstraintCliff, ...]:
    cliffs: list[ConstraintCliff] = []
    by_axis: dict[str, list[tuple[float, float, tuple[str, ...]]]] = {
        axis.factor_id: [] for axis in request.axes
    }
    for axis in request.axes:
        for point in points:
            shock_map = dict(point.shocks)
            if all(
                abs(shock_map[other.factor_id]) <= 1e-15
                for other in request.axes
                if other.factor_id != axis.factor_id
            ):
                by_axis[axis.factor_id].append(
                    (
                        shock_map[axis.factor_id],
                        point.output_value,
                        point.breached_constraint_ids,
                    )
                )
    scale = max(1.0, abs(request.response_model.baseline_value))
    for factor_id, rows in by_axis.items():
        rows.sort(key=lambda row: row[0])
        for left, middle, right in zip(rows, rows[1:], rows[2:]):
            curvature_jump = abs(right[1] - 2.0 * middle[1] + left[1]) / scale
            changed = set(left[2]) ^ set(middle[2]) | (set(middle[2]) ^ set(right[2]))
            if curvature_jump >= request.policy.cliff_relative_threshold or changed:
                cliffs.append(
                    ConstraintCliff(
                        factor_id=factor_id,
                        left_shock=middle[0],
                        right_shock=right[0],
                        relative_jump=curvature_jump,
                        constraint_ids=tuple(sorted(changed)),
                    )
                )
    return tuple(cliffs)


def _evaluate_surface_points(
    request: SensitivitySurfaceRequest,
) -> tuple[tuple[SurfacePoint, ...], int]:
    points: list[SurfacePoint] = []
    extrapolated_count = 0
    for values in itertools.product(*(axis.grid_values for axis in request.axes)):
        partial = {axis.factor_id: value for axis, value in zip(request.axes, values)}
        vector = _complete_vector(request, partial)
        output = evaluate_quadratic_response(request.response_model, vector)
        extrapolated = _is_extrapolated(request, partial)
        extrapolated_count += int(extrapolated)
        points.append(
            SurfacePoint(
                shocks=tuple(
                    (axis.factor_id, partial[axis.factor_id]) for axis in request.axes
                ),
                output_value=output,
                extrapolated=extrapolated,
                breached_constraint_ids=_point_constraints(request, output),
            )
        )
    return tuple(points), extrapolated_count


def _factor_sensitivities(
    request: SensitivitySurfaceRequest,
    factor_index: dict[str, int],
) -> tuple[FactorSensitivity, ...]:
    rows: list[FactorSensitivity] = []
    for axis in request.axes:
        index = factor_index[axis.factor_id]
        values = [
            evaluate_quadratic_response(
                request.response_model,
                _complete_vector(request, {axis.factor_id: value}),
            )
            for value in axis.grid_values
        ]
        rows.append(
            FactorSensitivity(
                factor_id=axis.factor_id,
                local_gradient=request.response_model.linear_coefficients[index],
                curvature=request.response_model.quadratic_matrix[index][index],
                main_effect_range=max(values) - min(values),
            )
        )
    return tuple(rows)


def _interaction_rows(
    request: SensitivitySurfaceRequest,
    factor_index: dict[str, int],
) -> tuple[InteractionSensitivity, ...]:
    rows: list[InteractionSensitivity] = []
    for left_index, left in enumerate(request.axes):
        for right in request.axes[left_index + 1 :]:
            coefficient = request.response_model.quadratic_matrix[
                factor_index[left.factor_id]
            ][factor_index[right.factor_id]]
            if abs(coefficient) > request.policy.interaction_tolerance:
                rows.append(
                    InteractionSensitivity(
                        factor_id_left=left.factor_id,
                        factor_id_right=right.factor_id,
                        interaction_coefficient=coefficient,
                    )
                )
    return tuple(rows)


def _surface_status(
    extrapolated_fraction: float,
    cliffs: tuple[ConstraintCliff, ...],
) -> tuple[S6State, tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    limitations: list[str] = []
    if extrapolated_fraction > 0:
        reasons.append("P9_STRESS_EXTRAPOLATION_UNQUALIFIED")
        limitations.append("some surface points are outside the observed factor domain")
    if cliffs:
        reasons.append("P9_STRESS_CONSTRAINT_DISCONTINUITY_FOUND")
        status = S6State.CONSTRAINT_DISCONTINUITY_FOUND
    elif extrapolated_fraction > 0:
        status = S6State.EXTRAPOLATION_LIMITED
    else:
        status = S6State.SUCCESS
    return status, tuple(reasons), tuple(limitations)


def build_sensitivity_surface(request: SensitivitySurfaceRequest) -> SensitivitySurfaceResult:
    """Evaluate the committed quadratic response surface on a declared factor grid."""

    evaluation_count = math.prod(len(axis.grid_values) for axis in request.axes)
    if evaluation_count > request.policy.maximum_evaluations:
        return SensitivitySurfaceResult(
            status=S6State.INVALID,
            model_id=request.response_model.model_id,
            points=(),
            factor_sensitivities=(),
            interactions=(),
            cliffs=(),
            evaluation_count=1,
            extrapolated_point_fraction=0.0,
            reason_codes=("P9_STRESS_EVALUATION_BUDGET_EXCEEDED",),
        )
    points, extrapolated_count = _evaluate_surface_points(request)
    factor_index = {
        factor_id: index
        for index, factor_id in enumerate(request.response_model.factor_ids)
    }
    sensitivities = _factor_sensitivities(request, factor_index)
    interactions = _interaction_rows(request, factor_index)
    cliffs = _detect_cliffs(request, points)
    extrapolated_fraction = extrapolated_count / len(points)
    status, reasons, limitations = _surface_status(extrapolated_fraction, cliffs)
    return SensitivitySurfaceResult(
        status=status,
        model_id=request.response_model.model_id,
        points=points,
        factor_sensitivities=sensitivities,
        interactions=interactions,
        cliffs=cliffs,
        evaluation_count=len(points),
        extrapolated_point_fraction=extrapolated_fraction,
        reason_codes=reasons,
        limitations=limitations,
    )
