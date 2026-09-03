"""P3.S7.M02 immutable population consistency validator."""
from __future__ import annotations

from collections import defaultdict
import math

from .distance import detect_clones, profile_fingerprint
from .errors import IntegrityError
from .hashing import sha256_hex, stable_id, stable_uint63
from .models import (
    CheckStatus,
    IssueSeverity,
    PopulationValidationRequest,
    PopulationValidationResult,
    ValidatedPopulationManifest,
    ValidationCheck,
    ValidationIssue,
    ValidationStatus,
)


class PopulationConsistencyValidator:
    """Validate a frozen population without repairing or mutating it."""

    module_id = "P3.S7.M02"

    def execute(self, request: PopulationValidationRequest) -> PopulationValidationResult:
        panel = request.person_seed_panel
        manifest = request.population_manifest
        report = request.personality_coverage_report
        config = request.population_representation_config
        self._verify_integrity(panel, manifest, report, config)
        issues: list[ValidationIssue] = []
        checks: list[ValidationCheck] = []

        def check(check_id: str, condition: bool, observed: str, expected: str, code: str) -> None:
            checks.append(
                ValidationCheck(
                    check_id=check_id,
                    status=CheckStatus.PASS if condition else CheckStatus.FAIL,
                    observed=observed,
                    expected=expected,
                    issue_codes=() if condition else (code,),
                )
            )
            if not condition:
                issues.append(
                    ValidationIssue(
                        issue_code=code,
                        severity=IssueSeverity.ERROR,
                        message=f"{check_id} failed",
                    )
                )

        check(
            "population_size",
            manifest.person_count >= config.minimum_population_size,
            str(manifest.person_count),
            f">={config.minimum_population_size}",
            "P3_S7_M02_POPULATION_BELOW_MINIMUM",
        )
        check(
            "weight_sum",
            abs(math.fsum(p.representation_weight for p in manifest.persons) - 1.0) <= config.sum_tolerance,
            repr(math.fsum(p.representation_weight for p in manifest.persons)),
            f"1.0±{config.sum_tolerance}",
            "P3_S7_M02_WEIGHT_SUM_INVALID",
        )
        check(
            "max_person_weight",
            max(p.representation_weight for p in manifest.persons) <= config.max_single_person_weight + config.sum_tolerance,
            repr(max(p.representation_weight for p in manifest.persons)),
            f"<={config.max_single_person_weight}",
            "P3_S7_M02_WEIGHT_CONCENTRATION",
        )
        ess = 1.0 / math.fsum(p.representation_weight ** 2 for p in manifest.persons)
        check(
            "effective_population_size",
            ess >= config.min_effective_population,
            repr(ess),
            f">={config.min_effective_population}",
            "P3_S7_M02_EFFECTIVE_POPULATION_TOO_LOW",
        )
        realized = defaultdict(list)
        for person in manifest.persons:
            realized[person.profile.role_family].append(person.representation_weight)
        realized_shares = {key: math.fsum(values) for key, values in realized.items()}
        share_failures = [
            family
            for family, target in config.target_role_family_shares.items()
            if abs(realized_shares.get(family, 0.0) - target) > config.role_family_share_tolerance
        ]
        check(
            "role_family_shares",
            not share_failures,
            json_like(realized_shares),
            json_like(config.target_role_family_shares),
            "P3_S7_M02_ROLE_FAMILY_SHARE_MISMATCH",
        )
        coverage = report.coverage
        coverage_ok = (
            coverage.overall_coverage_ratio >= config.minimum_overall_coverage_ratio
            and coverage.tag_coverage_ratio >= config.minimum_tag_coverage_ratio
            and coverage.role_coverage_ratio >= config.minimum_role_coverage_ratio
            and report.density_sufficiency_ratio >= config.minimum_density_sufficiency_ratio
        )
        check(
            "coverage_floor",
            coverage_ok,
            json_like({
                "overall": coverage.overall_coverage_ratio,
                "tag": coverage.tag_coverage_ratio,
                "role": coverage.role_coverage_ratio,
                "density": report.density_sufficiency_ratio,
            }),
            "all configured floors",
            "P3_S7_M02_COVERAGE_FLOOR_NOT_MET",
        )
        exact, near, near_share = detect_clones(manifest.persons, config)
        check(
            "exact_clone_policy",
            not exact,
            str(len(exact)),
            "0 exact clone groups",
            "P3_S7_M02_EXACT_CLONES_DETECTED",
        )
        check(
            "near_clone_share",
            near_share <= config.max_near_clone_person_share,
            repr(near_share),
            f"<={config.max_near_clone_person_share}",
            "P3_S7_M02_NEAR_CLONE_SHARE_EXCEEDED",
        )
        status = ValidationStatus.BLOCKED if any(i.severity is IssueSeverity.ERROR for i in issues) else ValidationStatus.READY
        payload = {
            "validation_status": status,
            "population_manifest_hash": manifest.manifest_hash,
            "checks": [item.model_dump(mode="json") for item in checks],
            "issues": [item.model_dump(mode="json") for item in issues],
            "exact_clone_groups": [item.model_dump(mode="json") for item in exact],
            "near_clone_pairs": [item.model_dump(mode="json") for item in near],
            "near_clone_person_share": near_share,
        }
        validated_hash = sha256_hex(payload, float_digits=config.profile_numeric_precision)
        validated = ValidatedPopulationManifest(
            validation_status=status,
            population_manifest=manifest,
            checks=tuple(checks),
            issues=tuple(issues),
            exact_clone_groups=exact,
            near_clone_pairs=near,
            near_clone_person_share=near_share,
            validated_manifest_hash=validated_hash,
            lineage_id=stable_id("lin", {"module": self.module_id, "validated_hash": validated_hash}),
        )
        return PopulationValidationResult(validated_population_manifest=validated)

    def _verify_integrity(self, panel, manifest, report, config) -> None:
        config_hash = sha256_hex(config.model_dump(mode="json"), float_digits=config.profile_numeric_precision)
        if manifest.representation_config_hash != config_hash:
            raise IntegrityError("P3_S7_M02_CONFIG_HASH_MISMATCH")
        seed_payload = {
            "creator_run_id": panel.creator_run_id,
            "population_id": panel.population_id,
            "records": [item.model_dump(mode="json") for item in panel.records],
        }
        expected_panel_hash = sha256_hex(seed_payload, float_digits=config.profile_numeric_precision)
        if panel.panel_hash != expected_panel_hash or manifest.person_seed_panel_hash != panel.panel_hash:
            raise IntegrityError("P3_S7_M02_PERSON_SEED_PANEL_HASH_MISMATCH")
        if panel.population_id != manifest.population_id:
            raise IntegrityError("P3_S7_M02_POPULATION_ID_MISMATCH")
        if panel.creator_run_id != manifest.creator_run_id or report.creator_run_id != manifest.creator_run_id:
            raise IntegrityError("P3_S7_M02_CREATOR_RUN_MISMATCH")
        if report.report_hash != manifest.coverage_report_hash:
            raise IntegrityError("P3_S7_M02_COVERAGE_REPORT_HASH_MISMATCH")
        if report.generation_round != manifest.final_generation_round:
            raise IntegrityError("P3_S7_M02_GENERATION_ROUND_MISMATCH")
        if report.candidate_count != manifest.person_count:
            raise IntegrityError("P3_S7_M02_CANDIDATE_COUNT_MISMATCH")
        if any(record.population_id != panel.population_id for record in panel.records):
            raise IntegrityError("P3_S7_M02_SEED_RECORD_POPULATION_ID_MISMATCH")
        panel_by_person = {item.person_id: item for item in panel.records}
        if set(panel_by_person) != {person.person_id for person in manifest.persons}:
            raise IntegrityError("P3_S7_M02_SEED_PERSON_SET_MISMATCH")
        expected_population_id = stable_id(
            "population",
            {
                "algorithm": config.population_id_algorithm,
                "creator_run_id": manifest.creator_run_id,
                "person_ids": sorted(person.person_id for person in manifest.persons),
                "config_hash": config_hash,
            },
            float_digits=config.profile_numeric_precision,
        )
        if expected_population_id != manifest.population_id:
            raise IntegrityError("P3_S7_M02_DERIVED_POPULATION_ID_MISMATCH")
        for person in manifest.persons:
            fingerprint = profile_fingerprint(person.profile, digits=config.profile_numeric_precision)
            expected_person_id = stable_id(
                "person",
                {
                    "algorithm": config.person_id_algorithm,
                    "architecture_revision": config.architecture_revision,
                    "creator_run_id": manifest.creator_run_id,
                    "candidate_id": person.candidate_id,
                    "profile_fingerprint": fingerprint,
                },
                float_digits=config.profile_numeric_precision,
            )
            if person.person_id != expected_person_id or person.profile_fingerprint != fingerprint:
                raise IntegrityError(f"P3_S7_M02_PERSON_ID_OR_FINGERPRINT_MISMATCH:{person.person_id}")
            namespace = {
                "algorithm": config.seed_algorithm,
                "creator_run_id": manifest.creator_run_id,
                "person_id": person.person_id,
                "freeze_contract": "P3.S7.v2",
            }
            expected_seed = stable_uint63(namespace, float_digits=config.profile_numeric_precision)
            seed_record = panel_by_person[person.person_id]
            if person.person_seed != expected_seed or seed_record.person_seed != expected_seed:
                raise IntegrityError(f"P3_S7_M02_SEED_MISMATCH:{person.person_id}")
            if seed_record.candidate_id != person.candidate_id:
                raise IntegrityError(f"P3_S7_M02_SEED_CANDIDATE_MISMATCH:{person.person_id}")
            if seed_record.seed_namespace_hash != sha256_hex(namespace):
                raise IntegrityError(f"P3_S7_M02_SEED_NAMESPACE_HASH_MISMATCH:{person.person_id}")
        realized = defaultdict(list)
        for person in manifest.persons:
            realized[person.profile.role_family].append(person.representation_weight)
        manifest_payload = {
            "creator_run_id": manifest.creator_run_id,
            "population_id": manifest.population_id,
            "final_generation_round": manifest.final_generation_round,
            "persons": [item.model_dump(mode="json") for item in manifest.persons],
            "target_role_family_shares": manifest.target_role_family_shares,
            "realized_role_family_shares": {family: math.fsum(values) for family, values in sorted(realized.items())},
            "weight_sum": math.fsum(person.representation_weight for person in manifest.persons),
            "max_person_weight": max(person.representation_weight for person in manifest.persons),
            "effective_population_size": 1.0 / math.fsum(person.representation_weight ** 2 for person in manifest.persons),
            "finalized_pool_hash": manifest.finalized_pool_hash,
            "coverage_report_hash": manifest.coverage_report_hash,
            "representation_config_hash": manifest.representation_config_hash,
            "person_seed_panel_hash": manifest.person_seed_panel_hash,
        }
        if manifest.manifest_hash != sha256_hex(manifest_payload, float_digits=config.profile_numeric_precision):
            raise IntegrityError("P3_S7_M02_POPULATION_MANIFEST_HASH_MISMATCH")


def json_like(value: object) -> str:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
