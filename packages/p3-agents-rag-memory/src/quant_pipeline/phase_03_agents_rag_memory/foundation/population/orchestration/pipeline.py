"""One-round orchestration for the P3 population foundation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..s5.consistency import PersonalityCandidateConsistencyChecker
from ..s5.generation import PersonalityCandidateGenerator
from ..s5.models import (
    ConsistencyRulesConfig,
    GenerationRequest,
    GenerationResult,
    ValidatedPersonalityCandidatePool,
    ValidationRequest,
)
from ..s6.controller import CoverageDensityController
from ..s6.metrics import PersonalityCoverageMetricCalculator
from ..s6.models import (
    CoverageCalculationRequest,
    CoverageCalculationResult,
    CoverageControlRequest,
    CoverageControlResult,
    CoverageDensityConfig,
    PersonalityTagRegistry as S6TagRegistry,
    PopulationGenerationStateV3,
    PriorPopulationGenerationStateV2,
)
from ..s7.builder import FixedPopulationBuilder
from ..s7.models import (
    FixedPopulationBuildRequest,
    FixedPopulationBuildResult,
    PopulationRepresentationConfig,
    PopulationValidationRequest,
    PopulationValidationResult,
)
from ..s7.validator import PopulationConsistencyValidator
from ..s8.builder import InitialSocialGraphBuilder
from ..s8.models import (
    InitialSocialGraphBuildRequest,
    InitialSocialGraphBuildResult,
    RelationshipPriorValidationRequest,
    RelationshipPriorValidationResult,
    SocialGraphConfig,
)
from ..s8.validator import RelationshipPriorValidator
from .bridges import (
    bridge_s5_validated_pool_to_s6,
    bridge_s6_finalized_to_s7,
    bridge_s6_report_to_s7,
    bridge_s7_population_to_s8,
    bridge_s7_seed_panel_to_s8,
)


class PopulationPipelineStatus(StrEnum):
    """Terminal state of one population-generation round."""

    CONTINUE_GENERATION = "CONTINUE_GENERATION"
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PopulationPipelineRequest:
    """Inputs needed to execute one deterministic S5-to-S8 round."""

    generation_request: GenerationRequest
    consistency_rules_config: ConsistencyRulesConfig
    coverage_density_config: CoverageDensityConfig
    prior_s6_state: PriorPopulationGenerationStateV2 | PopulationGenerationStateV3
    population_representation_config: PopulationRepresentationConfig
    social_graph_config: SocialGraphConfig


@dataclass(frozen=True, slots=True)
class PopulationPipelineResult:
    """All observable results from a population-generation round."""

    status: PopulationPipelineStatus
    generation: GenerationResult
    validated_candidates: ValidatedPersonalityCandidatePool
    coverage: CoverageCalculationResult
    control: CoverageControlResult
    population_build: FixedPopulationBuildResult | None = None
    population_validation: PopulationValidationResult | None = None
    social_graph_build: InitialSocialGraphBuildResult | None = None
    social_graph_validation: RelationshipPriorValidationResult | None = None


class PopulationFoundationPipeline:
    """Execute P3.S5 through P3.S8 for one generation round.

    When P3.S6 requests another round, the caller projects the returned state to P3.S5
    and invokes the pipeline again. The pipeline owns no hidden loop or global state.
    """

    def __init__(self, generator: PersonalityCandidateGenerator) -> None:
        self._generator = generator
        self._candidate_validator = PersonalityCandidateConsistencyChecker()
        self._coverage = PersonalityCoverageMetricCalculator()
        self._controller = CoverageDensityController()
        self._population_builder = FixedPopulationBuilder()
        self._population_validator = PopulationConsistencyValidator()
        self._graph_builder = InitialSocialGraphBuilder()
        self._graph_validator = RelationshipPriorValidator()

    async def execute(self, request: PopulationPipelineRequest) -> PopulationPipelineResult:
        generation = await self._generator.execute(request.generation_request)
        validated = self._candidate_validator.execute(
            ValidationRequest(
                personality_candidate_pool=generation.personality_candidate_pool,
                person_schema_policy=request.generation_request.person_schema_policy,
                consistency_rules_config=request.consistency_rules_config,
            )
        )

        coverage = self._calculate_coverage(request, validated)
        control = self._controller.execute(
            CoverageControlRequest(
                personality_coverage_report=coverage.personality_coverage_report,
                population_candidate_accumulator=coverage.population_candidate_accumulator,
                coverage_density_config=request.coverage_density_config,
            )
        )
        if control.finalized_personality_candidate_pool is None:
            return PopulationPipelineResult(
                status=PopulationPipelineStatus.CONTINUE_GENERATION,
                generation=generation,
                validated_candidates=validated,
                coverage=coverage,
                control=control,
            )

        population_build, population_validation = self._build_and_validate_population(request, coverage, control)
        if population_validation.validated_population_manifest.validation_status.value != "READY":
            return PopulationPipelineResult(
                status=PopulationPipelineStatus.BLOCKED,
                generation=generation,
                validated_candidates=validated,
                coverage=coverage,
                control=control,
                population_build=population_build,
                population_validation=population_validation,
            )

        graph_build, graph_validation = self._build_and_validate_graph(
            request,
            population_build,
            population_validation,
        )
        status = (
            PopulationPipelineStatus.READY
            if graph_validation.validated_initial_social_graph.validation_status.value == "READY"
            else PopulationPipelineStatus.BLOCKED
        )
        return PopulationPipelineResult(
            status=status,
            generation=generation,
            validated_candidates=validated,
            coverage=coverage,
            control=control,
            population_build=population_build,
            population_validation=population_validation,
            social_graph_build=graph_build,
            social_graph_validation=graph_validation,
        )

    def _calculate_coverage(
        self,
        request: PopulationPipelineRequest,
        validated: ValidatedPersonalityCandidatePool,
    ) -> CoverageCalculationResult:
        candidate_pool = bridge_s5_validated_pool_to_s6(validated)
        tag_registry = S6TagRegistry.model_validate(
            request.generation_request.personality_tag_registry.model_dump(mode="json"),
            strict=False,
        )
        return self._coverage.execute(
            CoverageCalculationRequest(
                validated_personality_candidate_pool=candidate_pool,
                personality_tag_registry=tag_registry,
                coverage_density_config=request.coverage_density_config,
                prior_population_generation_state=request.prior_s6_state,
            )
        )

    def _build_and_validate_population(
        self,
        request: PopulationPipelineRequest,
        coverage: CoverageCalculationResult,
        control: CoverageControlResult,
    ) -> tuple[FixedPopulationBuildResult, PopulationValidationResult]:
        finalized_pool = control.finalized_personality_candidate_pool
        assert finalized_pool is not None
        population_build = self._population_builder.execute(
            FixedPopulationBuildRequest(
                finalized_personality_candidate_pool=bridge_s6_finalized_to_s7(finalized_pool),
                personality_coverage_report=bridge_s6_report_to_s7(coverage.personality_coverage_report),
                population_representation_config=request.population_representation_config,
            )
        )
        population_validation = self._population_validator.execute(
            PopulationValidationRequest(
                person_seed_panel=population_build.person_seed_panel,
                population_manifest=population_build.population_manifest,
                personality_coverage_report=bridge_s6_report_to_s7(coverage.personality_coverage_report),
                population_representation_config=request.population_representation_config,
            )
        )
        return population_build, population_validation

    def _build_and_validate_graph(
        self,
        request: PopulationPipelineRequest,
        population_build: FixedPopulationBuildResult,
        population_validation: PopulationValidationResult,
    ) -> tuple[InitialSocialGraphBuildResult, RelationshipPriorValidationResult]:
        graph_build = self._graph_builder.execute(
            InitialSocialGraphBuildRequest(
                validated_population_manifest=bridge_s7_population_to_s8(
                    population_validation.validated_population_manifest
                ),
                person_seed_panel=bridge_s7_seed_panel_to_s8(population_build.person_seed_panel),
                social_graph_config=request.social_graph_config,
                personality_tag_registry=tuple(
                    sorted(request.generation_request.personality_tag_registry.tag_ids())
                ),
            )
        )
        graph_validation = self._graph_validator.execute(
            RelationshipPriorValidationRequest(
                initial_social_graph=graph_build.initial_social_graph,
                social_graph_config=request.social_graph_config,
            )
        )
        return graph_build, graph_validation
