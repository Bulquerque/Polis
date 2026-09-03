"""Declarative strategy grammar, objectives, constraints, and identity policy."""

from __future__ import annotations

from pydantic import Field

from ..domain.enums import ObjectiveFamily, TemplateId
from ..foundation.artifacts import FrozenModel


class TemplateDefinition(FrozenModel):
    template_id: TemplateId
    objective_family: ObjectiveFamily
    minimum_legs: int = Field(gt=0)
    maximum_legs: int = Field(gt=0)
    defined_risk_expected: bool
    enabled_in_wave1: bool = True
    description: str


class ObjectiveDefinition(FrozenModel):
    objective_family: ObjectiveFamily
    description: str
    ranking_semantics_forbidden: bool = True


class ConstraintDefinition(FrozenModel):
    policy_version: str
    max_legs: int
    max_expirations: int
    max_quantity: int
    naked_short_options_allowed: bool = False
    require_defined_risk: bool = True
    allowed_exercise_styles: tuple[str, ...]
    allowed_settlement_types: tuple[str, ...]


class StrategyIdentityPolicy(FrozenModel):
    policy_version: str
    content_fields: tuple[str, ...]
    order_invariant: bool = True
    row_index_forbidden: bool = True
