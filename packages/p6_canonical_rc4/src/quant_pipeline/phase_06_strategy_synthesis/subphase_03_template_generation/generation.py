"""Deterministic, budgeted Wave 1 strategy template generation."""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.enums import ObjectiveFamily, OptionType, TemplateId
from ..domain.models import CandidateGenerationTrace, RejectionRecord, StrategyCandidate, StrategyLeg
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id
from .builders import CandidatePair, make_candidate
from .family_generators import (
    generate_reserved,
    generate_single,
    generate_skew,
    generate_verticals,
    generate_volatility,
)
from .planning import TemplatePlan


def generate_template_family(
    family: str,
    plan: TemplatePlan,
    configuration: Phase6RunConfiguration,
) -> tuple[
    tuple[StrategyCandidate, ...],
    tuple[CandidateGenerationTrace, ...],
    tuple[RejectionRecord, ...],
]:
    """Generate one family under deterministic per-template budgets."""
    candidates: list[StrategyCandidate] = []
    traces: list[CandidateGenerationTrace] = []
    rejected: list[RejectionRecord] = []
    limit = configuration.budgets.max_candidates_per_template

    for underlying_id in plan.active_underlying_ids:
        try:
            generated = _generate_for_underlying(
                family,
                plan,
                underlying_id,
                configuration,
            )
            for candidate, trace in generated[:limit]:
                candidates.append(candidate)
                traces.append(trace)
        except (ValueError, IndexError) as exc:
            rejected.append(
                _rejection_record(family, underlying_id, exc)
            )
    return tuple(candidates), tuple(traces), tuple(rejected)


def _generate_for_underlying(
    family: str,
    plan: TemplatePlan,
    underlying_id: str,
    configuration: Phase6RunConfiguration,
) -> list[CandidatePair]:
    calls = plan.contracts(underlying_id, OptionType.CALL)
    puts = plan.contracts(underlying_id, OptionType.PUT)
    enabled = set(configuration.strategy.enabled_templates)
    output: list[CandidatePair] = []

    def add(
        template: TemplateId,
        objective: ObjectiveFamily,
        legs: Sequence[StrategyLeg],
    ) -> None:
        if template.value not in enabled:
            return
        if len(legs) > configuration.budgets.max_legs:
            return
        output.append(
            make_candidate(
                template,
                objective,
                underlying_id,
                tuple(legs),
                configuration,
                horizon_days=plan.horizon_days(underlying_id),
            )
        )

    generator = _FAMILY_GENERATORS.get(family)
    if generator is None:
        raise ValueError(f"unknown template family: {family}")
    generator(plan, underlying_id, calls, puts, configuration, add)
    return output


def _rejection_record(
    family: str,
    underlying_id: str,
    error: Exception,
) -> RejectionRecord:
    return RejectionRecord(
        rejection_id=stable_id("rejection", family, underlying_id, str(error)),
        stage="P6.S3",
        reason_code="P6_TEMPLATE_PRECONDITION_FAILED",
        details={
            "family": family,
            "underlying_id": underlying_id,
            "error": str(error),
        },
    )


_FAMILY_GENERATORS = {
    "single": generate_single,
    "vertical": generate_verticals,
    "volatility": generate_volatility,
    "skew": generate_skew,
    "term": generate_reserved,
    "overlay": generate_reserved,
}
