"""P3.S6.M01 deterministic coverage and density metrics."""
from __future__ import annotations
from math import fsum, sqrt
from .errors import AccumulatorConflictError, ConfigurationError, ContractError, StateCompatibilityError
from .hashing import sha256_hex, stable_short_id
from .models import (
    AccumulatorRecord, CandidateDensityMetric, CandidateRecord, CellType,
    CovarianceEntry, CoverageCalculationRequest, CoverageCalculationResult,
    CoverageCellStatus, CoverageSummary, GenerationMode, IntensityBin,
    PersonalityCoverageReport, PopulationCandidateAccumulator,
    PopulationGenerationStateV3, PriorPopulationGenerationStateV2,
    TagDistributionMetric,
)

class PersonalityCoverageMetricCalculator:
    """Accumulate accepted candidates and calculate deterministic population metrics."""

    module_id = "P3.S6.M01"

    def execute(self, request: CoverageCalculationRequest) -> CoverageCalculationResult:
        self._validate_registry_and_config(request)
        prior_records, prior_covered, prior_ratio, prior_patience = self._prior_state(request)
        accumulator, current_ids = self._merge_candidates(request, prior_records)
        candidates = tuple(record.candidate for record in accumulator.records)
        if not candidates:
            raise ContractError("P3_S6_M01_ZERO_CANDIDATES")
        weights = self._uniform_weights(candidates)
        vectors, assigned_values = self._effective_vectors(
            candidates, request.personality_tag_registry.tag_ids()
        )
        cells = self._coverage_cells(request, candidates, weights, assigned_values)
        coverage = self._coverage_summary(cells, prior_covered, prior_ratio)
        candidate_metrics = self._candidate_density_metrics(
            candidates,
            vectors,
            request.personality_tag_registry.category_by_tag(),
            request,
            set(current_ids),
        )
        tag_distributions, covariance = self._distribution_metrics(
            request.personality_tag_registry.tag_ids(), vectors, weights, request
        )
        mean_novelty = self._mean(item.novelty_distance for item in candidate_metrics)
        knn_values = [
            item.mean_knn_distance for item in candidate_metrics if item.mean_knn_distance is not None
        ]
        mean_knn = self._mean(knn_values) if knn_values else None
        mean_local_density = self._mean(item.local_density for item in candidate_metrics)
        density_ratio = self._mean(1.0 if item.density_sufficient else 0.0 for item in candidate_metrics)
        config_hash = sha256_hex(request.coverage_density_config.model_dump(mode="json"))
        payload = {
            "creator_run_id": accumulator.creator_run_id,
            "generation_round": accumulator.current_round,
            "mode": self._prior_mode(request),
            "candidate_count": len(candidates),
            "coverage": coverage.model_dump(mode="json"),
            "accumulator_hash": accumulator.accumulator_hash,
            "config_hash": config_hash,
        }
        report_hash = sha256_hex(payload)
        report = PersonalityCoverageReport(
            creator_run_id=accumulator.creator_run_id,
            generation_round=accumulator.current_round,
            mode=self._prior_mode(request),
            prior_patience_counter=prior_patience,
            candidate_count=len(candidates),
            current_round_candidate_ids=current_ids,
            candidate_weight_sum=fsum(weights.values()),
            coverage=coverage,
            cells=cells,
            candidate_metrics=candidate_metrics,
            tag_distributions=tag_distributions,
            covariance_entries=covariance,
            mean_novelty_distance=self._round(mean_novelty, request),
            mean_knn_distance=(self._round(mean_knn, request) if mean_knn is not None else None),
            mean_local_density=self._round(mean_local_density, request),
            density_sufficiency_ratio=self._round(density_ratio, request),
            config_hash=config_hash,
            accumulator_hash=accumulator.accumulator_hash,
            report_hash=report_hash,
            lineage_id=stable_short_id("lin", {"module": self.module_id, "report": report_hash}),
        )
        return CoverageCalculationResult(
            personality_coverage_report=report,
            population_candidate_accumulator=accumulator,
        )

    def _validate_registry_and_config(self, request: CoverageCalculationRequest) -> None:
        tag_ids = set(request.personality_tag_registry.tag_ids())
        required = {item.tag_id for item in request.coverage_density_config.tag_coverage_requirements}
        pairwise = {
            tag
            for item in request.coverage_density_config.pairwise_tag_cells
            for tag in (item.left_tag_id, item.right_tag_id)
        }
        unknown = sorted((required | pairwise) - tag_ids)
        if unknown:
            raise ConfigurationError(f"P3_S6_M01_UNKNOWN_CONFIG_TAGS:{','.join(unknown)}")
        candidate_tags = {
            assignment.tag_id
            for candidate in request.validated_personality_candidate_pool.accepted_candidates
            for assignment in candidate.profile.tags
        }
        unknown_candidate_tags = sorted(candidate_tags - tag_ids)
        if unknown_candidate_tags:
            raise ContractError(
                f"P3_S6_M01_UNKNOWN_CANDIDATE_TAGS:{','.join(unknown_candidate_tags)}"
            )
        categories = set(request.personality_tag_registry.category_by_tag().values())
        unknown_categories = sorted(set(request.coverage_density_config.tag_category_weights) - categories)
        if unknown_categories:
            raise ConfigurationError(
                f"P3_S6_M01_UNKNOWN_TAG_CATEGORIES:{','.join(unknown_categories)}"
            )

    def _prior_state(self, request: CoverageCalculationRequest):
        state = request.prior_population_generation_state
        if isinstance(state, PriorPopulationGenerationStateV2):
            if state.accepted_candidate_ids:
                raise StateCompatibilityError(
                    "P3_S6_M01_LEGACY_STATE_MISSING_ACCUMULATOR; use state v3 or the S5 projection only at the S5 boundary"
                )
            return (), frozenset(), 0.0, 0
        if state.terminal_status is not None:
            raise StateCompatibilityError("P3_S6_M01_TERMINAL_STATE_CANNOT_CONTINUE")
        accumulator_ids = tuple(record.candidate.candidate_id for record in state.accumulator.records)
        if accumulator_ids != state.accepted_candidate_ids:
            raise StateCompatibilityError("P3_S6_M01_STATE_ACCUMULATOR_ID_MISMATCH")
        if state.accumulator.creator_run_id != state.creator_run_id:
            raise StateCompatibilityError("P3_S6_M01_STATE_CREATOR_RUN_MISMATCH")
        if state.accumulator.current_round != state.generation_round:
            raise StateCompatibilityError("P3_S6_M01_STATE_ROUND_MISMATCH")
        if len(state.covered_cell_ids) != len(set(state.covered_cell_ids)):
            raise StateCompatibilityError("P3_S6_M01_DUPLICATE_COVERED_CELL")
        return (
            state.accumulator.records,
            frozenset(state.covered_cell_ids),
            state.previous_coverage_ratio,
            state.patience_counter,
        )

    def _prior_mode(self, request: CoverageCalculationRequest) -> GenerationMode:
        return request.prior_population_generation_state.mode

    def _merge_candidates(self, request: CoverageCalculationRequest, prior_records):
        current = request.validated_personality_candidate_pool.accepted_candidates
        creator_ids = {item.creator_run_id for item in current}
        state_creator = request.prior_population_generation_state.creator_run_id
        if creator_ids and creator_ids != {state_creator}:
            raise ContractError("P3_S6_M01_CREATOR_RUN_MISMATCH")
        if not current and not prior_records:
            raise ContractError("P3_S6_M01_ZERO_CANDIDATES")
        rounds = {item.generation_round for item in current}
        if current and len(rounds) != 1:
            raise ContractError("P3_S6_M01_MULTIPLE_GENERATION_ROUNDS")
        current_round = next(iter(rounds), request.prior_population_generation_state.generation_round)
        prior = request.prior_population_generation_state
        if isinstance(prior, PopulationGenerationStateV3):
            if current_round != prior.generation_round + 1:
                raise ContractError("P3_S6_M01_NON_CONTIGUOUS_GENERATION_ROUND")
        elif current_round != prior.generation_round:
            raise ContractError("P3_S6_M01_INITIAL_ROUND_MISMATCH")
        merged = {record.candidate.candidate_id: record for record in prior_records}
        current_ids = []
        for candidate in sorted(current, key=lambda item: item.candidate_id):
            content_hash = sha256_hex(candidate.model_dump(mode="json"))
            existing = merged.get(candidate.candidate_id)
            if existing is not None:
                if existing.candidate_content_hash != content_hash:
                    raise AccumulatorConflictError("P3_S6_M01_CANDIDATE_ID_CONTENT_CONFLICT")
                continue
            merged[candidate.candidate_id] = AccumulatorRecord(
                candidate=candidate,
                first_seen_round=current_round,
                source_pool_hash=request.validated_personality_candidate_pool.source_pool_hash,
                candidate_content_hash=content_hash,
            )
            current_ids.append(candidate.candidate_id)
        records = tuple(merged[key] for key in sorted(merged))
        accumulator_payload = [record.model_dump(mode="json") for record in records]
        accumulator_hash = sha256_hex(accumulator_payload)
        accumulator = PopulationCandidateAccumulator(
            creator_run_id=state_creator,
            current_round=current_round,
            records=records,
            accumulator_hash=accumulator_hash,
            lineage_id=stable_short_id("lin", {"module": self.module_id, "accumulator": accumulator_hash}),
        )
        return accumulator, tuple(current_ids)

    @staticmethod
    def _uniform_weights(candidates: tuple[CandidateRecord, ...]) -> dict[str, float]:
        value = 1.0 / len(candidates)
        return {candidate.candidate_id: value for candidate in candidates}

    @staticmethod
    def _effective_vectors(candidates, tag_ids):
        vectors = {}
        assigned = {}
        for candidate in candidates:
            values = {tag_id: 0.0 for tag_id in tag_ids}
            assigned_values = {}
            for item in candidate.profile.tags:
                effective = item.intensity * item.confidence
                values[item.tag_id] = effective
                assigned_values[item.tag_id] = effective
            vectors[candidate.candidate_id] = values
            assigned[candidate.candidate_id] = assigned_values
        return vectors, assigned

    def _coverage_cells(self, request, candidates, weights, assigned_values):
        config = request.coverage_density_config
        bins = config.bin_map()
        cells = []
        for requirement in config.tag_coverage_requirements:
            for bin_id in requirement.required_bin_ids:
                interval = bins[bin_id]
                matching = [
                    candidate.candidate_id
                    for candidate in candidates
                    if requirement.tag_id in assigned_values[candidate.candidate_id]
                    and interval.contains(assigned_values[candidate.candidate_id][requirement.tag_id])
                ]
                cells.append(self._cell(
                    f"tag:{requirement.tag_id}:bin:{bin_id}", CellType.TAG_BIN, matching, weights
                ))
        for role_family in config.required_role_families:
            matching = [
                candidate.candidate_id
                for candidate in candidates
                if candidate.profile.role_family == role_family
            ]
            cells.append(self._cell(f"role:{role_family}", CellType.ROLE_FAMILY, matching, weights))
        for pair in config.pairwise_tag_cells:
            matching = []
            for candidate in candidates:
                values = assigned_values[candidate.candidate_id]
                if (
                    values.get(pair.left_tag_id, -1.0) >= pair.left_min_effective_value
                    and values.get(pair.right_tag_id, -1.0) >= pair.right_min_effective_value
                ):
                    matching.append(candidate.candidate_id)
            cells.append(self._cell(f"pair:{pair.cell_id}", CellType.PAIRWISE_TAG, matching, weights))
        return tuple(sorted(cells, key=lambda item: item.cell_id))

    @staticmethod
    def _cell(cell_id, cell_type, matching, weights):
        mass = fsum(weights[candidate_id] for candidate_id in matching)
        return CoverageCellStatus(
            cell_id=cell_id,
            cell_type=cell_type,
            covered=bool(matching),
            candidate_count=len(matching),
            weighted_mass=min(1.0, max(0.0, mass)),
        )

    def _coverage_summary(self, cells, prior_covered, prior_ratio):
        by_type = {
            cell_type: [item for item in cells if item.cell_type is cell_type]
            for cell_type in CellType
        }
        ratio = lambda items: self._mean(1.0 if item.covered else 0.0 for item in items) if items else 1.0
        covered = frozenset(item.cell_id for item in cells if item.covered)
        known = frozenset(item.cell_id for item in cells)
        unknown_prior = prior_covered - known
        if unknown_prior:
            raise StateCompatibilityError("P3_S6_M01_PRIOR_STATE_REFERENCES_UNKNOWN_CELLS")
        new = tuple(sorted(covered - prior_covered))
        overall = ratio(list(cells))
        marginal = len(new) / len(cells) if cells else 0.0
        return CoverageSummary(
            tag_coverage_ratio=ratio(by_type[CellType.TAG_BIN]),
            role_coverage_ratio=ratio(by_type[CellType.ROLE_FAMILY]),
            pairwise_coverage_ratio=ratio(by_type[CellType.PAIRWISE_TAG]),
            overall_coverage_ratio=overall,
            prior_coverage_ratio=prior_ratio,
            marginal_coverage_gain=marginal,
            new_covered_cell_ids=new,
            missing_cell_ids=tuple(sorted(known - covered)),
        )

    def _candidate_density_metrics(self, candidates, vectors, category_by_tag, request, current_ids):
        config = request.coverage_density_config
        ordered_tags = request.personality_tag_registry.tag_ids()
        dimension_weights = [
            config.tag_category_weights.get(
                category_by_tag[tag_id], config.default_tag_category_weight
            )
            for tag_id in ordered_tags
        ]
        metrics = []
        for candidate in candidates:
            distances = []
            source = vectors[candidate.candidate_id]
            for other in candidates:
                if other.candidate_id == candidate.candidate_id:
                    continue
                target = vectors[other.candidate_id]
                distances.append(self._distance(source, target, ordered_tags, dimension_weights))
            distances.sort()
            neighbor_count = min(config.knn_k, len(distances))
            selected = distances[:neighbor_count]
            mean_knn = self._mean(selected) if selected else None
            novelty = distances[0] if distances else 0.0
            local_density = 0.0 if mean_knn is None else 1.0 / (config.distance_floor + mean_knn)
            metrics.append(CandidateDensityMetric(
                candidate_id=candidate.candidate_id,
                novelty_distance=self._round(novelty, request),
                mean_knn_distance=(self._round(mean_knn, request) if mean_knn is not None else None),
                local_density=self._round(local_density, request),
                neighbor_count=neighbor_count,
                density_sufficient=mean_knn is not None and mean_knn <= config.density_radius,
                is_current_round_candidate=candidate.candidate_id in current_ids,
            ))
        return tuple(sorted(metrics, key=lambda item: item.candidate_id))

    @staticmethod
    def _distance(source, target, ordered_tags, weights):
        denominator = fsum(weights)
        if denominator <= 0.0:
            raise ConfigurationError("P3_S6_M01_ZERO_DIMENSION_WEIGHT")
        squared = fsum(
            weight * (source[tag] - target[tag]) ** 2
            for tag, weight in zip(ordered_tags, weights)
        )
        return sqrt(squared / denominator)

    def _distribution_metrics(self, tag_ids, vectors, weights, request):
        means = {}
        distributions = []
        for tag_id in tag_ids:
            mean = fsum(weights[candidate_id] * vector[tag_id] for candidate_id, vector in vectors.items())
            means[tag_id] = mean
            variance = fsum(
                weights[candidate_id] * (vector[tag_id] - mean) ** 2
                for candidate_id, vector in vectors.items()
            )
            distributions.append(TagDistributionMetric(
                tag_id=tag_id,
                weighted_mean=self._round(mean, request),
                weighted_variance=self._round(variance, request),
            ))
        covariance = []
        ordered = tuple(tag_ids)
        for index, left in enumerate(ordered):
            for right in ordered[index:]:
                value = fsum(
                    weights[candidate_id]
                    * (vectors[candidate_id][left] - means[left])
                    * (vectors[candidate_id][right] - means[right])
                    for candidate_id in vectors
                )
                covariance.append(CovarianceEntry(
                    left_tag_id=left,
                    right_tag_id=right,
                    covariance=self._round(value, request),
                ))
        return tuple(distributions), tuple(covariance)

    @staticmethod
    def _mean(values):
        values = list(values)
        return fsum(values) / len(values) if values else 0.0

    @staticmethod
    def _round(value, request):
        return round(value, request.coverage_density_config.output_rounding_digits)
