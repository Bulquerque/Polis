"""Implementation of P3.S5.M02 personality_candidate_consistency_checker."""
from __future__ import annotations

from collections.abc import Callable

from .hashing import sha256_hex, stable_short_id
from .models import (
    CandidateDecision,
    CandidateRecord,
    CandidateValidationResult,
    RuleViolation,
    Severity,
    ValidatedPersonalityCandidatePool,
    ValidationRequest,
)

Rule = Callable[[CandidateRecord, ValidationRequest], tuple[RuleViolation, ...]]

class PersonalityCandidateConsistencyChecker:
    """Apply deterministic canonical rules; never mutate or repair candidates."""

    MODULE_ID = "P3.S5.M02"

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {
            "life_stage_experience": self._life_stage_experience,
            "occupation_role": self._occupation_role,
            "role_resources": self._role_resources,
            "institution_tool_access": self._institution_tool_access,
            "role_objectives": self._role_objectives,
            "education_literacy": self._education_literacy,
        }

    def execute(self, request: ValidationRequest) -> ValidatedPersonalityCandidatePool:
        enabled = request.consistency_rules_config.enabled_rules
        unknown = set(enabled) - set(self._rules)
        if unknown:
            raise ValueError(f"unknown consistency rules: {sorted(unknown)}")

        results: list[CandidateValidationResult] = []
        accepted: list[CandidateRecord] = []
        rejected: list[str] = []
        for candidate in request.personality_candidate_pool.candidates:
            violations: list[RuleViolation] = list(self._tag_registry_invariant(candidate, request))
            for rule_id in enabled:
                violations.extend(self._rules[rule_id](candidate, request))
            decision = CandidateDecision.REJECTED if violations else CandidateDecision.ACCEPTED
            results.append(
                CandidateValidationResult(
                    candidate_id=candidate.candidate_id,
                    decision=decision,
                    violations=tuple(violations),
                )
            )
            if decision is CandidateDecision.ACCEPTED:
                accepted.append(candidate)
            else:
                rejected.append(candidate.candidate_id)

        source_hash = sha256_hex(request.personality_candidate_pool.model_dump(mode="json"))
        return ValidatedPersonalityCandidatePool(
            source_pool_hash=source_hash,
            accepted_candidates=tuple(accepted),
            rejected_candidate_ids=tuple(rejected),
            validation_results=tuple(results),
            rules_version=request.consistency_rules_config.rules_version,
            lineage_id=stable_short_id(
                "lin",
                {
                    "module_id": self.MODULE_ID,
                    "source_hash": source_hash,
                    "rules_version": request.consistency_rules_config.rules_version,
                },
            ),
        )


    def _tag_registry_invariant(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        allowed = frozenset(request.person_schema_policy.allowed_tag_ids)
        unknown = sorted({tag.tag_id for tag in candidate.profile.tags} - allowed)
        if not unknown:
            return ()
        return (
            self._violation(
                "tag_registry_invariant",
                "profile.tags",
                "UNKNOWN_PERSONALITY_TAG",
                unknown,
                "all tag_id values must exist in personality_tag_registry",
            ),
        )

    @staticmethod
    def _violation(
        rule_id: str,
        field_path: str,
        reason_code: str,
        observed: object,
        expected: str,
    ) -> RuleViolation:
        return RuleViolation(
            rule_id=rule_id,
            severity=Severity.ERROR,
            field_path=field_path,
            reason_code=reason_code,
            observed_value=str(observed),
            expected_constraint=expected,
        )

    def _life_stage_experience(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        band = request.person_schema_policy.experience_map().get(profile.life_stage)
        if band is None:
            return (
                self._violation(
                    "life_stage_experience",
                    "profile.life_stage",
                    "UNKNOWN_LIFE_STAGE",
                    profile.life_stage,
                    "registered life_stage",
                ),
            )
        if not band.minimum_years <= profile.years_experience <= band.maximum_years:
            return (
                self._violation(
                    "life_stage_experience",
                    "profile.years_experience",
                    "EXPERIENCE_OUTSIDE_LIFE_STAGE_BAND",
                    profile.years_experience,
                    f"[{band.minimum_years}, {band.maximum_years}]",
                ),
            )
        return ()

    def _occupation_role(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        role = request.person_schema_policy.role_map().get(profile.economic_role)
        if role is None:
            return (
                self._violation(
                    "occupation_role",
                    "profile.economic_role",
                    "UNKNOWN_ECONOMIC_ROLE",
                    profile.economic_role,
                    "registered economic_role",
                ),
            )
        violations = []
        if profile.role_family != role.role_family:
            violations.append(
                self._violation(
                    "occupation_role",
                    "profile.role_family",
                    "ROLE_FAMILY_MISMATCH",
                    profile.role_family,
                    role.role_family,
                )
            )
        if profile.occupation_family not in role.allowed_occupation_families:
            violations.append(
                self._violation(
                    "occupation_role",
                    "profile.occupation_family",
                    "OCCUPATION_NOT_ALLOWED_FOR_ROLE",
                    profile.occupation_family,
                    ",".join(role.allowed_occupation_families),
                )
            )
        return tuple(violations)

    def _role_resources(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        role = request.person_schema_policy.role_map().get(profile.economic_role)
        if role is None:
            return ()
        violations: list[RuleViolation] = []
        missing = sorted(set(role.required_resource_flags) - set(profile.resources.flags))
        if missing:
            violations.append(
                self._violation(
                    "role_resources",
                    "profile.resources.flags",
                    "MISSING_REQUIRED_RESOURCE_FLAGS",
                    missing,
                    ",".join(role.required_resource_flags),
                )
            )
        capabilities = profile.capabilities.model_dump(mode="python")
        for capability_name, minimum in role.minimum_capabilities.items():
            observed = float(capabilities.get(capability_name, 0.0))
            if observed < minimum:
                violations.append(
                    self._violation(
                        "role_resources",
                        f"profile.capabilities.{capability_name}",
                        "MINIMUM_ROLE_CAPABILITY_NOT_MET",
                        observed,
                        f">= {minimum}",
                    )
                )
        return tuple(violations)

    def _institution_tool_access(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        if "institutional_data_access" not in {tag.tag_id for tag in profile.tags}:
            return ()
        if profile.institution_type in (None, "none", "independent"):
            return (
                self._violation(
                    "institution_tool_access",
                    "profile.institution_type",
                    "INSTITUTIONAL_ACCESS_WITHOUT_INSTITUTION",
                    profile.institution_type,
                    "non-independent institution_type",
                ),
            )
        return ()

    def _role_objectives(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        role = request.person_schema_policy.role_map().get(profile.economic_role)
        if role is None:
            return ()
        violations = []
        objective_ids = {item.objective_id for item in profile.objective_weights}
        disallowed = sorted(objective_ids - set(role.allowed_objectives))
        if disallowed:
            violations.append(
                self._violation(
                    "role_objectives",
                    "profile.objective_weights",
                    "OBJECTIVE_NOT_ALLOWED_FOR_ROLE",
                    disallowed,
                    ",".join(role.allowed_objectives),
                )
            )
        total = sum(item.weight for item in profile.objective_weights)
        tolerance = request.person_schema_policy.objective_sum_tolerance
        if abs(total - 1.0) > tolerance:
            violations.append(
                self._violation(
                    "role_objectives",
                    "profile.objective_weights",
                    "OBJECTIVE_WEIGHTS_DO_NOT_SUM_TO_ONE",
                    total,
                    f"1.0 ± {tolerance}",
                )
            )
        return tuple(violations)

    def _education_literacy(
        self, candidate: CandidateRecord, request: ValidationRequest
    ) -> tuple[RuleViolation, ...]:
        profile = candidate.profile
        policy = request.person_schema_policy
        rank = policy.education_rank.get(profile.education_level)
        if rank is None:
            return (
                self._violation(
                    "education_literacy",
                    "profile.education_level",
                    "UNKNOWN_EDUCATION_LEVEL",
                    profile.education_level,
                    "registered education_level",
                ),
            )
        violations = []
        capabilities = profile.capabilities.model_dump(mode="python")
        for capability_name, thresholds in policy.capability_minimum_education_rank.items():
            level = float(capabilities.get(capability_name, 0.0))
            required_rank = 0
            for threshold, threshold_rank in sorted(
                ((float(key), value) for key, value in thresholds.items())
            ):
                if level >= threshold:
                    required_rank = max(required_rank, threshold_rank)
            if rank < required_rank:
                violations.append(
                    self._violation(
                        "education_literacy",
                        f"profile.capabilities.{capability_name}",
                        "CAPABILITY_INCONSISTENT_WITH_EDUCATION",
                        level,
                        f"education rank >= {required_rank}",
                    )
                )
        return tuple(violations)
