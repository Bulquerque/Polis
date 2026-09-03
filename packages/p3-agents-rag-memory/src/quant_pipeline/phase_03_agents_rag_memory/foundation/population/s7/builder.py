"""P3.S7.M01 deterministic population freeze."""
from __future__ import annotations

from collections import defaultdict
import math

from .errors import ContractError, PopulationConstructionError
from .hashing import sha256_hex, stable_id, stable_uint63, upstream_sha256_hex
from .distance import profile_fingerprint
from .models import (
    CreatorProvenance,
    FixedPopulationBuildRequest,
    FixedPopulationBuildResult,
    FrozenPerson,
    PersonSeedPanel,
    PersonSeedRecord,
    PopulationManifest,
)


class FixedPopulationBuilder:
    """Freeze a finalized S6 pool into stable persons, seeds and weights."""

    module_id = "P3.S7.M01"

    def execute(self, request: FixedPopulationBuildRequest) -> FixedPopulationBuildResult:
        pool = request.finalized_personality_candidate_pool
        report = request.personality_coverage_report
        config = request.population_representation_config
        self._validate_upstream(pool, report, config)
        config_hash = sha256_hex(config.model_dump(mode="json"), float_digits=config.profile_numeric_precision)
        preliminary = []
        for candidate in sorted(pool.candidates, key=lambda item: item.candidate_id):
            fingerprint = profile_fingerprint(candidate.profile, digits=config.profile_numeric_precision)
            person_id = stable_id(
                "person",
                {
                    "algorithm": config.person_id_algorithm,
                    "architecture_revision": config.architecture_revision,
                    "creator_run_id": pool.creator_run_id,
                    "candidate_id": candidate.candidate_id,
                    "profile_fingerprint": fingerprint,
                },
                float_digits=config.profile_numeric_precision,
            )
            seed_namespace = {
                "algorithm": config.seed_algorithm,
                "creator_run_id": pool.creator_run_id,
                "person_id": person_id,
                "freeze_contract": "P3.S7.v2",
            }
            seed = stable_uint63(seed_namespace, float_digits=config.profile_numeric_precision)
            preliminary.append((candidate, fingerprint, person_id, seed, seed_namespace))
        person_ids = sorted(item[2] for item in preliminary)
        population_id = stable_id(
            "population",
            {
                "algorithm": config.population_id_algorithm,
                "creator_run_id": pool.creator_run_id,
                "person_ids": person_ids,
                "config_hash": config_hash,
            },
            float_digits=config.profile_numeric_precision,
        )
        weights = self._weights(preliminary, config)
        persons = []
        seed_records = []
        for candidate, fingerprint, person_id, seed, seed_namespace in preliminary:
            provenance = CreatorProvenance(
                creator_run_id=candidate.creator_run_id,
                generation_round=candidate.generation_round,
                generation_mode=candidate.generation_mode,
                provider_id=candidate.provider_id,
                model_id=candidate.model_id,
                prompt_id=candidate.prompt_id,
                prompt_version=candidate.prompt_version,
                prompt_hash=candidate.prompt_hash,
                request_hash=candidate.request_hash,
                response_hash=candidate.response_hash,
                candidate_lineage_id=candidate.lineage_id,
            )
            person_lineage = stable_id(
                "lin",
                {"module": self.module_id, "person_id": person_id, "candidate": candidate.lineage_id},
            )
            persons.append(
                FrozenPerson(
                    person_id=person_id,
                    candidate_id=candidate.candidate_id,
                    representation_weight=weights[person_id],
                    profile=candidate.profile,
                    creator_provenance=provenance,
                    person_seed=seed,
                    profile_fingerprint=fingerprint,
                    lineage_id=person_lineage,
                )
            )
            seed_records.append(
                PersonSeedRecord(
                    person_id=person_id,
                    candidate_id=candidate.candidate_id,
                    person_seed=seed,
                    seed_algorithm=config.seed_algorithm,
                    seed_namespace_hash=sha256_hex(seed_namespace),
                    population_id=population_id,
                    lineage_id=stable_id("lin", {"module": self.module_id, "seed": seed, "person": person_id}),
                )
            )
        persons_tuple = tuple(sorted(persons, key=lambda item: item.person_id))
        seed_records_tuple = tuple(sorted(seed_records, key=lambda item: item.person_id))
        seed_payload = {
            "creator_run_id": pool.creator_run_id,
            "population_id": population_id,
            "records": [item.model_dump(mode="json") for item in seed_records_tuple],
        }
        panel_hash = sha256_hex(seed_payload, float_digits=config.profile_numeric_precision)
        seed_panel = PersonSeedPanel(
            creator_run_id=pool.creator_run_id,
            population_id=population_id,
            records=seed_records_tuple,
            panel_hash=panel_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "panel_hash": panel_hash}),
        )
        realized = self._realized_shares(persons_tuple)
        weight_sum = math.fsum(person.representation_weight for person in persons_tuple)
        ess = 1.0 / math.fsum(person.representation_weight ** 2 for person in persons_tuple)
        manifest_payload = {
            "creator_run_id": pool.creator_run_id,
            "population_id": population_id,
            "final_generation_round": pool.final_generation_round,
            "persons": [item.model_dump(mode="json") for item in persons_tuple],
            "target_role_family_shares": config.target_role_family_shares,
            "realized_role_family_shares": realized,
            "weight_sum": weight_sum,
            "max_person_weight": max(person.representation_weight for person in persons_tuple),
            "effective_population_size": ess,
            "finalized_pool_hash": pool.pool_hash,
            "coverage_report_hash": report.report_hash,
            "representation_config_hash": config_hash,
            "person_seed_panel_hash": panel_hash,
        }
        manifest_hash = sha256_hex(manifest_payload, float_digits=config.profile_numeric_precision)
        manifest = PopulationManifest(
            creator_run_id=pool.creator_run_id,
            population_id=population_id,
            final_generation_round=pool.final_generation_round,
            person_count=len(persons_tuple),
            persons=persons_tuple,
            target_role_family_shares=dict(sorted(config.target_role_family_shares.items())),
            realized_role_family_shares=realized,
            weight_sum=weight_sum,
            max_person_weight=max(person.representation_weight for person in persons_tuple),
            effective_population_size=ess,
            finalized_pool_hash=pool.pool_hash,
            coverage_report_hash=report.report_hash,
            representation_config_hash=config_hash,
            person_seed_panel_hash=panel_hash,
            manifest_hash=manifest_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "manifest_hash": manifest_hash}),
        )
        return FixedPopulationBuildResult(person_seed_panel=seed_panel, population_manifest=manifest)

    def _validate_upstream(self, pool, report, config) -> None:
        expected_pool_hash = upstream_sha256_hex(
            [candidate.model_dump(mode="json") for candidate in pool.candidates]
        )
        if expected_pool_hash != pool.pool_hash:
            raise ContractError("P3_S7_M01_FINALIZED_POOL_HASH_MISMATCH")
        if pool.coverage_report_hash != report.report_hash:
            raise ContractError("P3_S7_M01_COVERAGE_REPORT_HASH_MISMATCH")
        if pool.creator_run_id != report.creator_run_id:
            raise ContractError("P3_S7_M01_CREATOR_RUN_MISMATCH")
        if pool.final_generation_round != report.generation_round:
            raise ContractError("P3_S7_M01_GENERATION_ROUND_MISMATCH")
        if len(pool.candidates) != report.candidate_count:
            raise ContractError("P3_S7_M01_CANDIDATE_COUNT_MISMATCH")
        candidate_ids = [candidate.candidate_id for candidate in pool.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ContractError("P3_S7_M01_DUPLICATE_CANDIDATE_ID")
        if len(pool.candidates) < config.minimum_population_size:
            raise PopulationConstructionError("P3_S7_M01_POPULATION_BELOW_MINIMUM")
        known_families = set(config.target_role_family_shares)
        actual_families = {candidate.profile.role_family for candidate in pool.candidates}
        unknown = actual_families - known_families
        missing = known_families - actual_families
        if unknown:
            raise PopulationConstructionError(f"P3_S7_M01_UNKNOWN_ROLE_FAMILIES:{','.join(sorted(unknown))}")
        if missing:
            raise PopulationConstructionError(f"P3_S7_M01_MISSING_ROLE_FAMILIES:{','.join(sorted(missing))}")
        for candidate in pool.candidates:
            objective_sum = math.fsum(item.weight for item in candidate.profile.objective_weights)
            if abs(objective_sum - 1.0) > config.objective_weight_sum_tolerance:
                raise PopulationConstructionError(
                    f"P3_S7_M01_OBJECTIVE_WEIGHT_SUM_INVALID:{candidate.candidate_id}"
                )
        coverage = report.coverage
        if coverage.overall_coverage_ratio < config.minimum_overall_coverage_ratio:
            raise PopulationConstructionError("P3_S7_M01_OVERALL_COVERAGE_BELOW_FLOOR")
        if coverage.tag_coverage_ratio < config.minimum_tag_coverage_ratio:
            raise PopulationConstructionError("P3_S7_M01_TAG_COVERAGE_BELOW_FLOOR")
        if coverage.role_coverage_ratio < config.minimum_role_coverage_ratio:
            raise PopulationConstructionError("P3_S7_M01_ROLE_COVERAGE_BELOW_FLOOR")
        if report.density_sufficiency_ratio < config.minimum_density_sufficiency_ratio:
            raise PopulationConstructionError("P3_S7_M01_DENSITY_BELOW_FLOOR")

    def _weights(self, preliminary, config) -> dict[str, float]:
        grouped = defaultdict(list)
        for candidate, _, person_id, _, _ in preliminary:
            grouped[candidate.profile.role_family].append(person_id)
        result: dict[str, float] = {}
        for family, share in sorted(config.target_role_family_shares.items()):
            person_ids = sorted(grouped[family])
            base = share / len(person_ids)
            assigned = [base] * max(len(person_ids) - 1, 0)
            final = share - math.fsum(assigned)
            family_weights = [*assigned, final]
            if max(family_weights) > config.max_single_person_weight + config.sum_tolerance:
                raise PopulationConstructionError(
                    f"P3_S7_M01_FAMILY_COUNT_INSUFFICIENT_FOR_WEIGHT_CAP:{family}"
                )
            result.update(zip(person_ids, family_weights, strict=True))
        total = math.fsum(result.values())
        if abs(total - 1.0) > config.sum_tolerance:
            raise PopulationConstructionError("P3_S7_M01_WEIGHT_SUM_UNSTABLE")
        return result

    @staticmethod
    def _realized_shares(persons) -> dict[str, float]:
        shares = defaultdict(list)
        for person in persons:
            shares[person.profile.role_family].append(person.representation_weight)
        return {family: math.fsum(values) for family, values in sorted(shares.items())}
