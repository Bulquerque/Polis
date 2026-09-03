"""Versioned authority for every quantitative rule used across P3."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from pydantic import Field, model_validator

from ..contracts import ContractModel, content_hash


class FormulaDefinition(ContractModel):
    formula_id: Annotated[str, Field(pattern=r"^p3\.[a-z0-9_.-]+$")]
    formula_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    description: Annotated[str, Field(min_length=1)]
    input_grain: tuple[str, ...]
    output_grain: tuple[str, ...]
    parameters: tuple[str, ...] = ()
    owner_module_ids: tuple[str, ...]
    expression: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def unique_fields(self) -> "FormulaDefinition":
        for fields, name in (
            (self.input_grain, "input_grain"),
            (self.output_grain, "output_grain"),
            (self.parameters, "parameters"),
            (self.owner_module_ids, "owner_module_ids"),
        ):
            if len(fields) != len(set(fields)):
                raise ValueError(f"{name} values must be unique")
        return self

    @property
    def formula_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class FormulaRegistry(ContractModel):
    registry_id: str = "P3_FORMULA_REGISTRY"
    registry_version: str = "1.0.0"
    formulas: tuple[FormulaDefinition, ...]

    @model_validator(mode="after")
    def unique_formulas(self) -> "FormulaRegistry":
        keys = [(item.formula_id, item.formula_version) for item in self.formulas]
        if len(keys) != len(set(keys)):
            raise ValueError("formula id/version pairs must be unique")
        return self

    def require(self, formula_id: str, version: str | None = None) -> FormulaDefinition:
        matches = [item for item in self.formulas if item.formula_id == formula_id]
        if version is not None:
            matches = [item for item in matches if item.formula_version == version]
        if len(matches) != 1:
            raise KeyError(f"formula not uniquely resolved: {formula_id}@{version or 'latest'}")
        return matches[0]


def _formula(
    formula_id: str,
    description: str,
    owners: Iterable[str],
    expression: str,
    *,
    input_grain: tuple[str, ...],
    output_grain: tuple[str, ...],
    parameters: tuple[str, ...] = (),
) -> FormulaDefinition:
    return FormulaDefinition(
        formula_id=formula_id,
        formula_version="1.0.0",
        description=description,
        input_grain=input_grain,
        output_grain=output_grain,
        parameters=parameters,
        owner_module_ids=tuple(owners),
        expression=expression,
    )


canonical_formula_registry = FormulaRegistry(
    formulas=(
        _formula(
            "p3.population.coverage",
            "Weighted coverage across required role and tag cells.",
            ("P3.S6.M01", "P3.S6.M02"),
            "sum(required_cell_weight * covered) / sum(required_cell_weight)",
            input_grain=("candidate_id", "coverage_cell"),
            output_grain=("generation_round",),
            parameters=("minimum_cell_count", "required_cell_weight"),
        ),
        _formula(
            "p3.population.representation_weight",
            "Normalized representation weights for the frozen population.",
            ("P3.S7.M01", "P3.S7.M02"),
            "raw_weight / sum(raw_weight)",
            input_grain=("candidate_id",),
            output_grain=("person_id",),
            parameters=("normalization_tolerance",),
        ),
        _formula(
            "p3.social.initial_edge_probability",
            "Seeded prior probability for an initial social edge.",
            ("P3.S8.M01", "P3.S8.M02"),
            "sigmoid(intercept + homophily + institution + role + geography)",
            input_grain=("source_person_id", "target_person_id"),
            output_grain=("edge_id",),
            parameters=("intercept", "homophily", "institution", "role", "geography"),
        ),
        _formula(
            "p3.activation.score",
            "Deterministic activation score before any LLM call.",
            ("P3.S19.M01",),
            "weighted_sum(salience, relevance, attention, availability) - fatigue_penalty",
            input_grain=("person_id", "stimulus_id", "cycle_id"),
            output_grain=("activation_id",),
            parameters=("threshold", "budget", "fatigue_penalty"),
        ),
        _formula(
            "p3.retrieval.rerank",
            "Normalized evidence-aware reranking of memory, RAG and GraphRAG results.",
            ("P3.S20.M05",),
            "normalized_relevance + temporal_fit + evidence_quality + personal_relevance",
            input_grain=("person_id", "evidence_id"),
            output_grain=("person_id", "evidence_id"),
            parameters=("source_weights", "top_k", "minimum_score"),
        ),
        _formula(
            "p3.emergence.belief_distribution",
            "Representation-weighted belief distribution with effective sample size.",
            ("P3.S27.M01",),
            "weighted_distribution(belief, representation_weight)",
            input_grain=("person_id", "underlying", "proposition", "horizon", "as_of"),
            output_grain=("underlying", "proposition", "horizon", "as_of"),
            parameters=("minimum_ess", "window_cycles"),
        ),
        _formula(
            "p3.emergence.information_asymmetry",
            "Observed-exposure asymmetry across the represented population.",
            ("P3.S27.M02",),
            "weighted_dispersion(observed_exposure)",
            input_grain=("person_id", "evidence_id", "cycle_id"),
            output_grain=("underlying", "proposition", "horizon", "as_of"),
            parameters=("minimum_ess",),
        ),
        _formula(
            "p3.emergence.cascade",
            "Causal-chain cascade metrics over stimulus, delivery, activation and belief IDs.",
            ("P3.S27.M03",),
            "connected_components(causal_event_graph)",
            input_grain=("causal_event_id",),
            output_grain=("cascade_id", "as_of"),
            parameters=("maximum_gap", "minimum_depth"),
        ),
        _formula(
            "p3.society.vector",
            "Canonical society vector at underlying-proposition-horizon-as_of grain.",
            ("P3.S28.M01", "P3.S28.M02", "P3.S28.M03"),
            "compose(distribution, attention, asymmetry, cascade, tag_projection, quality)",
            input_grain=("underlying", "proposition", "horizon", "as_of", "person_id"),
            output_grain=("underlying", "proposition", "horizon", "as_of"),
            parameters=("minimum_ess", "minimum_coverage", "quality_threshold"),
        ),
        _formula(
            "p3.products.disagreement",
            "Attribution of population disagreement to evidence, interpretation, horizon and access.",
            ("P3.S29.M01",),
            "multi_label_driver_attribution(distribution, evidence, access, horizon)",
            input_grain=("underlying", "proposition", "horizon", "as_of", "person_id"),
            output_grain=("underlying", "proposition", "horizon", "as_of"),
            parameters=("driver_threshold",),
        ),
    )
)
