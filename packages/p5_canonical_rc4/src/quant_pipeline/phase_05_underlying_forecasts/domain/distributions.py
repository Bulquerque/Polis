"""Predictive distributions crossing P5 subphase boundaries."""
from __future__ import annotations

from math import isclose
from typing import Annotated, Literal, TypeAlias

import numpy as np
from pydantic import Field, model_validator
from scipy.optimize import brentq
from scipy.stats import gennorm, norm, t

from .core import FrozenModel


class QuantilePoint(FrozenModel):
    level: float = Field(gt=0.0, lt=1.0)
    value: float


class PointDistribution(FrozenModel):
    kind: Literal["POINT"] = "POINT"
    value: float


class QuantileDistribution(FrozenModel):
    kind: Literal["QUANTILES"] = "QUANTILES"
    quantiles: tuple[QuantilePoint, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_quantiles(self) -> "QuantileDistribution":
        levels = tuple(item.level for item in self.quantiles)
        values = tuple(item.value for item in self.quantiles)
        if levels != tuple(sorted(levels)) or len(levels) != len(set(levels)):
            raise ValueError("quantile levels must be strictly increasing")
        if any(left > right for left, right in zip(values, values[1:], strict=False)):
            raise ValueError("quantile values must be monotonic")
        return self


class ParametricDistribution(FrozenModel):
    kind: Literal["PARAMETRIC"] = "PARAMETRIC"
    family: Literal["NORMAL", "STUDENT_T", "GED"]
    location: float
    scale: float = Field(gt=0.0)
    degrees_of_freedom: float | None = Field(default=None, gt=2.0)
    shape_parameter: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_family(self) -> "ParametricDistribution":
        if self.family == "STUDENT_T" and self.degrees_of_freedom is None:
            raise ValueError("Student-t requires degrees_of_freedom")
        if self.family == "GED" and self.shape_parameter is None:
            raise ValueError("GED requires shape_parameter")
        if self.family == "NORMAL" and (
            self.degrees_of_freedom is not None or self.shape_parameter is not None
        ):
            raise ValueError("Normal distribution must not declare shape parameters")
        if self.family == "STUDENT_T" and self.shape_parameter is not None:
            raise ValueError("Student-t must not declare GED shape_parameter")
        if self.family == "GED" and self.degrees_of_freedom is not None:
            raise ValueError("GED must not declare degrees_of_freedom")
        return self


class MixtureComponent(FrozenModel):
    family: Literal["NORMAL", "STUDENT_T", "GED"]
    weight: float = Field(gt=0.0, le=1.0)
    location: float
    scale: float = Field(gt=0.0)
    degrees_of_freedom: float | None = Field(default=None, gt=2.0)
    shape_parameter: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_family(self) -> "MixtureComponent":
        ParametricDistribution(
            family=self.family,
            location=self.location,
            scale=self.scale,
            degrees_of_freedom=self.degrees_of_freedom,
            shape_parameter=self.shape_parameter,
        )
        return self


class MixtureDistribution(FrozenModel):
    kind: Literal["MIXTURE"] = "MIXTURE"
    components: tuple[MixtureComponent, ...] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_weights(self) -> "MixtureDistribution":
        if not isclose(sum(item.weight for item in self.components), 1.0, abs_tol=1e-8):
            raise ValueError("mixture weights must sum to one")
        return self


class EmpiricalDistribution(FrozenModel):
    kind: Literal["EMPIRICAL"] = "EMPIRICAL"
    samples: tuple[float, ...] = Field(min_length=2, max_length=2048)


class ScenarioPoint(FrozenModel):
    scenario_id: str = Field(min_length=1)
    value: float
    probability: float = Field(gt=0.0, le=1.0)


class ScenarioDistribution(FrozenModel):
    kind: Literal["SCENARIOS"] = "SCENARIOS"
    scenarios: tuple[ScenarioPoint, ...] = Field(min_length=2, max_length=2048)

    @model_validator(mode="after")
    def validate_probability(self) -> "ScenarioDistribution":
        identifiers = tuple(item.scenario_id for item in self.scenarios)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scenario_id values must be unique")
        probability = sum(item.probability for item in self.scenarios)
        if not isclose(probability, 1.0, abs_tol=1e-8):
            raise ValueError("scenario probabilities must sum to one")
        return self


ForecastDistribution: TypeAlias = Annotated[
    PointDistribution
    | QuantileDistribution
    | ParametricDistribution
    | MixtureDistribution
    | EmpiricalDistribution
    | ScenarioDistribution,
    Field(discriminator="kind"),
]


def point_value(distribution: ForecastDistribution) -> float:
    if isinstance(distribution, PointDistribution):
        return distribution.value
    if isinstance(distribution, QuantileDistribution):
        return quantile_value(distribution, 0.5)
    if isinstance(distribution, ParametricDistribution):
        return distribution.location
    if isinstance(distribution, MixtureDistribution):
        return float(sum(item.weight * item.location for item in distribution.components))
    if isinstance(distribution, EmpiricalDistribution):
        return float(np.median(distribution.samples))
    return float(sum(item.value * item.probability for item in distribution.scenarios))


def quantile_value(distribution: ForecastDistribution, level: float) -> float:
    if not 0.0 < level < 1.0:
        raise ValueError("quantile level must be between zero and one")
    if isinstance(distribution, PointDistribution):
        return distribution.value
    if isinstance(distribution, QuantileDistribution):
        levels = np.asarray([item.level for item in distribution.quantiles], dtype=float)
        values = np.asarray([item.value for item in distribution.quantiles], dtype=float)
        return float(np.interp(level, levels, values))
    if isinstance(distribution, ParametricDistribution):
        return _parametric_ppf(distribution, level)
    if isinstance(distribution, MixtureDistribution):
        return _mixture_ppf(distribution, level)
    if isinstance(distribution, EmpiricalDistribution):
        return float(np.quantile(distribution.samples, level))
    cumulative = 0.0
    for item in sorted(distribution.scenarios, key=lambda row: row.value):
        cumulative += item.probability
        if cumulative >= level:
            return item.value
    return max(distribution.scenarios, key=lambda row: row.value).value


def distribution_cdf(distribution: ForecastDistribution, value: float) -> float:
    if isinstance(distribution, PointDistribution):
        return float(value >= distribution.value)
    if isinstance(distribution, QuantileDistribution):
        values = np.asarray([item.value for item in distribution.quantiles], dtype=float)
        levels = np.asarray([item.level for item in distribution.quantiles], dtype=float)
        return float(np.interp(value, values, levels, left=0.0, right=1.0))
    if isinstance(distribution, ParametricDistribution):
        return _parametric_cdf(distribution, value)
    if isinstance(distribution, MixtureDistribution):
        return float(sum(item.weight * _component_cdf(item, value) for item in distribution.components))
    if isinstance(distribution, EmpiricalDistribution):
        return float(np.mean(np.asarray(distribution.samples) <= value))
    return float(sum(
        item.probability for item in distribution.scenarios if item.value <= value
    ))


def _parametric_ppf(distribution: ParametricDistribution, level: float) -> float:
    if distribution.family == "NORMAL":
        return float(norm.ppf(level, loc=distribution.location, scale=distribution.scale))
    if distribution.family == "STUDENT_T":
        return float(t.ppf(
            level,
            df=distribution.degrees_of_freedom,
            loc=distribution.location,
            scale=distribution.scale,
        ))
    return float(gennorm.ppf(
        level,
        beta=distribution.shape_parameter,
        loc=distribution.location,
        scale=distribution.scale,
    ))


def _parametric_cdf(distribution: ParametricDistribution, value: float) -> float:
    if distribution.family == "NORMAL":
        return float(norm.cdf(value, loc=distribution.location, scale=distribution.scale))
    if distribution.family == "STUDENT_T":
        return float(t.cdf(
            value,
            df=distribution.degrees_of_freedom,
            loc=distribution.location,
            scale=distribution.scale,
        ))
    return float(gennorm.cdf(
        value,
        beta=distribution.shape_parameter,
        loc=distribution.location,
        scale=distribution.scale,
    ))


def _component_cdf(component: MixtureComponent, value: float) -> float:
    return _parametric_cdf(ParametricDistribution(
        family=component.family,
        location=component.location,
        scale=component.scale,
        degrees_of_freedom=component.degrees_of_freedom,
        shape_parameter=component.shape_parameter,
    ), value)


def _mixture_ppf(distribution: MixtureDistribution, level: float) -> float:
    lower = min(item.location - 100.0 * item.scale for item in distribution.components)
    upper = max(item.location + 100.0 * item.scale for item in distribution.components)
    objective = lambda value: sum(
        item.weight * _component_cdf(item, value) for item in distribution.components
    ) - level
    return float(brentq(objective, lower, upper, maxiter=200))
