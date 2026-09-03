"""Typed bridges between the P3.S5, P3.S6, P3.S7 and P3.S8 contracts.

The subphases intentionally own distinct Pydantic models. A boundary bridge therefore
serializes the producer's declared JSON surface and validates it against the consumer's
model. This is the only approved coercion point; domain services remain strict.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..s5.models import ValidatedPersonalityCandidatePool as S5ValidatedPool
from ..s6.models import (
    FinalizedPersonalityCandidatePool as S6FinalizedPool,
    PersonalityCoverageReport as S6CoverageReport,
    ValidatedPersonalityCandidatePool as S6ValidatedPool,
)
from ..s7.models import (
    FinalizedPersonalityCandidatePool as S7FinalizedPool,
    PersonSeedPanel as S7PersonSeedPanel,
    PersonalityCoverageReport as S7CoverageReport,
    ValidatedPopulationManifest as S7ValidatedPopulationManifest,
)
from ..s8.models import (
    PersonSeedPanel as S8PersonSeedPanel,
    ValidatedPopulationManifest as S8ValidatedPopulationManifest,
)
from .errors import PopulationCompatibilityError

ModelT = TypeVar("ModelT", bound=BaseModel)


def _bridge(value: BaseModel, target: type[ModelT], boundary: str) -> ModelT:
    try:
        payload = value.model_dump(mode="json")
        return target.model_validate(payload, strict=False)
    except (ValidationError, TypeError, ValueError) as exc:
        raise PopulationCompatibilityError(f"{boundary}: {exc}") from exc


def bridge_s5_validated_pool_to_s6(value: S5ValidatedPool) -> S6ValidatedPool:
    return _bridge(value, S6ValidatedPool, "P3.S5 -> P3.S6 validated candidate pool")


def bridge_s6_finalized_to_s7(value: S6FinalizedPool) -> S7FinalizedPool:
    return _bridge(value, S7FinalizedPool, "P3.S6 -> P3.S7 finalized candidate pool")


def bridge_s6_report_to_s7(value: S6CoverageReport) -> S7CoverageReport:
    return _bridge(value, S7CoverageReport, "P3.S6 -> P3.S7 coverage report")


def bridge_s7_population_to_s8(
    value: S7ValidatedPopulationManifest,
) -> S8ValidatedPopulationManifest:
    return _bridge(value, S8ValidatedPopulationManifest, "P3.S7 -> P3.S8 population manifest")


def bridge_s7_seed_panel_to_s8(value: S7PersonSeedPanel) -> S8PersonSeedPanel:
    return _bridge(value, S8PersonSeedPanel, "P3.S7 -> P3.S8 person seed panel")
