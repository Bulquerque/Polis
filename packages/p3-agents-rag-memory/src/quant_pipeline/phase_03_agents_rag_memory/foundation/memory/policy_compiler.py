from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from .errors import MemoryPolicyError, S14Issue
from .hashing import hash_value, stable_id
from .models import (
    ArtifactStatus,
    MemoryAccessConfig,
    MemoryAccessPolicy,
    PersonSchemaPolicyView,
    Phase3RunSnapshotView,
    RetrievalBudget,
    ScopePolicy,
    ScoreFormula,
    TemporalMemoryPolicy,
    TypePolicy,
)

Logger = Callable[[str, dict[str, object]], None]


def _log(logger: Logger | None, event: str, **fields: object) -> None:
    if logger is not None:
        logger(event, fields)


@dataclass(frozen=True, slots=True)
class ParsedMemoryPolicyInputs:
    config: MemoryAccessConfig
    person: PersonSchemaPolicyView
    snapshot: Phase3RunSnapshotView


@dataclass(frozen=True, slots=True)
class MemoryPolicyInputParser:
    def parse(
        self,
        *,
        memory_access_config: object,
        person_schema_policy: object,
        phase3_run_snapshot: object,
    ) -> ParsedMemoryPolicyInputs:
        try:
            config = (
                memory_access_config
                if isinstance(memory_access_config, MemoryAccessConfig)
                else MemoryAccessConfig.model_validate(memory_access_config)
            )
            person = (
                person_schema_policy
                if isinstance(person_schema_policy, PersonSchemaPolicyView)
                else PersonSchemaPolicyView.model_validate(person_schema_policy)
            )
            snapshot = (
                phase3_run_snapshot
                if isinstance(phase3_run_snapshot, Phase3RunSnapshotView)
                else Phase3RunSnapshotView.model_validate(phase3_run_snapshot)
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise MemoryPolicyError(
                [
                    S14Issue(
                        code="P3_S14_M01_INPUT_INVALID",
                        message="P3.S14.M01 input validation failed.",
                        details={"error": str(exc)},
                    )
                ]
            ) from exc
        return ParsedMemoryPolicyInputs(config=config, person=person, snapshot=snapshot)


@dataclass(frozen=True, slots=True)
class MemoryOntologyCompatibilityValidator:
    def validate(self, parsed: ParsedMemoryPolicyInputs) -> None:
        config_types = {row.memory_type for row in parsed.config.type_policies}
        config_scopes = {row.visibility_scope for row in parsed.config.scope_policies}
        if config_types != set(parsed.person.allowed_memory_types) or config_scopes != set(
            parsed.person.allowed_visibility_scopes
        ):
            raise MemoryPolicyError(
                [
                    S14Issue(
                        code="P3_S14_M01_PERSON_SCHEMA_INCOMPATIBLE",
                        message="Memory ontology differs between configuration and person schema policy.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class MemoryPolicyAssembler:
    def assemble(self, parsed: ParsedMemoryPolicyInputs) -> MemoryAccessPolicy:
        config, person, snapshot = parsed.config, parsed.person, parsed.snapshot
        type_policies = tuple(
            TypePolicy(
                memory_type=row.memory_type,
                enabled=row.enabled,
                half_life_days=row.half_life_days,
                max_per_query=row.max_per_query,
            )
            for row in sorted(config.type_policies, key=lambda row: row.memory_type.value)
        )
        scope_policies = tuple(
            ScopePolicy(
                visibility_scope=row.visibility_scope,
                retrievable=row.retrievable,
                requires_relationship=row.requires_relationship,
                audit_only=row.audit_only,
            )
            for row in sorted(config.scope_policies, key=lambda row: row.visibility_scope.value)
        )
        formula = ScoreFormula(
            formula_id=config.formula_id,
            formula_version=config.formula_version,
            factors=("relevance", "recency", "importance", "repetition", "significance"),
            weights=config.factor_weights,
            recency_decay="EXPONENTIAL_HALF_LIFE",
        )
        budgets = RetrievalBudget.model_validate(config.budgets.model_dump())
        temporal = TemporalMemoryPolicy(
            pit_filter_required=True,
            same_cycle_back_edge_forbidden=True,
            future_record_policy=config.future_record_policy,
        )
        core = {
            "run_id": snapshot.run_id,
            "snapshot_id": snapshot.snapshot_id,
            "as_of_time": snapshot.as_of,
            "policy_version": config.policy_version,
            "person_schema_policy_hash": person.content_hash,
            "score_formula": formula,
            "budgets": budgets,
            "type_policies": type_policies,
            "scope_policies": scope_policies,
            "temporal_policy": temporal,
            "audit_memory_separate": True,
        }
        content_hash = hash_value(core)
        return MemoryAccessPolicy(
            artifact_id=stable_id("memory-policy", snapshot.run_id, snapshot.snapshot_id, content_hash),
            module_id="P3.S14.M01",
            run_id=snapshot.run_id,
            snapshot_id=snapshot.snapshot_id,
            as_of_time=snapshot.as_of,
            policy_id=stable_id("policy", config.policy_version, person.content_hash, snapshot.snapshot_hash),
            policy_version=config.policy_version,
            person_schema_policy_hash=person.content_hash,
            score_formula=formula,
            budgets=budgets,
            type_policies=type_policies,
            scope_policies=scope_policies,
            temporal_policy=temporal,
            audit_memory_separate=True,
            status=ArtifactStatus.READY,
            content_hash=content_hash,
            lineage_id=stable_id("lineage-memory-policy", snapshot.lineage_id, person.lineage_id, content_hash),
        )


@dataclass(frozen=True, slots=True)
class MemoryPolicyCompiler:
    logger: Logger | None = None
    parser: MemoryPolicyInputParser = MemoryPolicyInputParser()
    validator: MemoryOntologyCompatibilityValidator = MemoryOntologyCompatibilityValidator()
    assembler: MemoryPolicyAssembler = MemoryPolicyAssembler()

    def compile(self, **inputs: object) -> MemoryAccessPolicy:
        _log(self.logger, "module_started", module_id="P3.S14.M01")
        parsed = self.parser.parse(**inputs)
        self.validator.validate(parsed)
        result = self.assembler.assemble(parsed)
        _log(
            self.logger,
            "module_succeeded",
            module_id="P3.S14.M01",
            run_id=result.run_id,
            snapshot_id=result.snapshot_id,
            status=result.status.value,
            output_record_count=1,
        )
        return result
