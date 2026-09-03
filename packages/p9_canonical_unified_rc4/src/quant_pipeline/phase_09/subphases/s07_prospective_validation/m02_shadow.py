"""P9.S7.M02 — isolated shadow champion/challenger orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import Field, field_validator, model_validator

from .canonical import payload_sha256
from .contracts import NonEmptyStr, StrictModel
from .errors import ContractError
from .m01_prequential import PrequentialRecord


class DeploymentStage(StrEnum):
    SHADOW_ONLY = "SHADOW_ONLY"
    PAPER_EXECUTION = "PAPER_EXECUTION"
    LIMITED_CAPITAL = "LIMITED_CAPITAL"
    FULL_PRODUCTION = "FULL_PRODUCTION"
    QUARANTINED = "QUARANTINED"


class PolicyRole(StrEnum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"


class PolicySpecification(StrictModel):
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    role: PolicyRole
    code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_budget_units: int = Field(gt=0)
    seed_entropy: int = Field(ge=0)
    authorized_stage: DeploymentStage
    authorization_ref: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_authorization(self) -> "PolicySpecification":
        capital_stages = {
            DeploymentStage.LIMITED_CAPITAL,
            DeploymentStage.FULL_PRODUCTION,
        }
        if self.authorized_stage in capital_stages:
            if self.authorization_ref is None:
                raise ValueError("capital-bearing stages require authorization_ref")
        return self


class ShadowPlanEntry(StrictModel):
    cohort_id: NonEmptyStr
    prediction_event_id: NonEmptyStr
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    role: PolicyRole
    information_set_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage: DeploymentStage
    resource_budget_units: int = Field(gt=0)
    seed_entropy: int = Field(ge=0)


class ShadowExecutionPlan(StrictModel):
    entries: tuple[ShadowPlanEntry, ...]
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyExecutionOutput(StrictModel):
    cohort_id: NonEmptyStr
    prediction_event_id: NonEmptyStr
    policy_id: NonEmptyStr
    policy_version: NonEmptyStr
    information_set_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage: DeploymentStage
    started_at: datetime
    completed_at: datetime
    output_artifact_id: NonEmptyStr | None = None
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    execution_status: NonEmptyStr
    resource_units_used: int = Field(ge=0)
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @field_validator("started_at", "completed_at")
    @classmethod
    def times_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("execution clocks must be UTC")
        return value

    @model_validator(mode="after")
    def validate_output(self) -> "PolicyExecutionOutput":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        has_output = self.output_artifact_id is not None and self.output_sha256 is not None
        if self.execution_status == "SUCCESS" and not has_output:
            raise ValueError("successful execution requires output artifact and hash")
        return self


class ShadowComparabilityReceipt(StrictModel):
    comparable_cohort_count: int = Field(ge=0)
    incomplete_cohort_count: int = Field(ge=0)
    policy_ids: tuple[NonEmptyStr, ...]
    common_snapshot_verified: bool
    isolation_verified: bool
    reason_codes: tuple[NonEmptyStr, ...] = ()
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyExecutor(Protocol):
    """Injected executor. S7 never embeds or discovers trading code."""

    def __call__(self, entry: ShadowPlanEntry) -> PolicyExecutionOutput: ...


def build_shadow_execution_plan(
    records: tuple[PrequentialRecord, ...],
    champion: PolicySpecification,
    challengers: tuple[PolicySpecification, ...],
    allowed_policy_ids: frozenset[str] | None = None,
) -> ShadowExecutionPlan:
    """Create a deterministic plan using a common information snapshot per cohort."""

    if champion.role is not PolicyRole.CHAMPION:
        raise ContractError("champion policy must have CHAMPION role")
    if any(policy.role is not PolicyRole.CHALLENGER for policy in challengers):
        raise ContractError("all challenger policies must have CHALLENGER role")
    policies = (champion,) + tuple(sorted(challengers, key=lambda item: item.policy_id))
    policy_ids = [policy.policy_id for policy in policies]
    if len(policy_ids) != len(set(policy_ids)):
        raise ContractError("duplicate policy_id")
    if allowed_policy_ids is not None and not set(policy_ids).issubset(allowed_policy_ids):
        raise ContractError("P9_LIVE_UNAUTHORIZED_DEPLOYMENT_STAGE")

    entries: list[ShadowPlanEntry] = []
    ordered_records = sorted(
        records,
        key=lambda item: (item.prediction.issued_at, item.prediction.event_id),
    )
    for record in ordered_records:
        for policy in policies:
            entries.append(
                ShadowPlanEntry(
                    cohort_id=record.prediction.cohort_id,
                    prediction_event_id=record.prediction.event_id,
                    policy_id=policy.policy_id,
                    policy_version=policy.policy_version,
                    role=policy.role,
                    information_set_hash=record.prediction.information_set_hash,
                    stage=policy.authorized_stage,
                    resource_budget_units=policy.resource_budget_units,
                    seed_entropy=policy.seed_entropy,
                )
            )
    payload = [entry.model_dump(mode="json") for entry in entries]
    return ShadowExecutionPlan(entries=tuple(entries), plan_sha256=payload_sha256(payload))


def execute_shadow_plan(
    plan: ShadowExecutionPlan,
    executor: PolicyExecutor | Callable[[ShadowPlanEntry], PolicyExecutionOutput],
    clock: Callable[[], datetime],
) -> tuple[PolicyExecutionOutput, ...]:
    """Execute each plan entry independently through an injected executor."""

    outputs: list[PolicyExecutionOutput] = []
    for entry in plan.entries:
        try:
            output = executor(entry)
        except Exception as exc:  # boundary shell: preserve failure, never create economic fallback
            now = clock()
            if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
                raise ContractError("shadow execution clock must return UTC") from exc
            output = PolicyExecutionOutput(
                cohort_id=entry.cohort_id,
                prediction_event_id=entry.prediction_event_id,
                policy_id=entry.policy_id,
                policy_version=entry.policy_version,
                information_set_hash=entry.information_set_hash,
                stage=entry.stage,
                started_at=now,
                completed_at=now,
                execution_status="FAILED_INTERNAL",
                resource_units_used=0,
                reason_codes=(f"P9_LIVE_POLICY_EXECUTION_EXCEPTION_{type(exc).__name__.upper()}",),
            )
        identity_mismatch = (
            output.policy_id != entry.policy_id
            or output.prediction_event_id != entry.prediction_event_id
        )
        if identity_mismatch:
            raise ContractError("P9_LIVE_POLICY_STATE_CONTAMINATION")
        if output.information_set_hash != entry.information_set_hash:
            raise ContractError("P9_LIVE_COMMON_SNAPSHOT_MISMATCH")
        if output.resource_units_used > entry.resource_budget_units:
            raise ContractError("policy exceeded resource budget")
        outputs.append(output)
    return tuple(outputs)


def evaluate_shadow_comparability(
    plan: ShadowExecutionPlan,
    outputs: tuple[PolicyExecutionOutput, ...],
) -> ShadowComparabilityReceipt:
    """Verify common snapshots and complete policy coverage per prediction cohort."""

    expected = {(entry.prediction_event_id, entry.policy_id): entry for entry in plan.entries}
    actual = {(output.prediction_event_id, output.policy_id): output for output in outputs}
    if len(actual) != len(outputs):
        raise ContractError("duplicate policy output")
    unknown = set(actual) - set(expected)
    if unknown:
        raise ContractError("unexpected policy outputs")

    expected_policy_ids = tuple(sorted({entry.policy_id for entry in plan.entries}))
    cohorts: dict[str, list[PolicyExecutionOutput]] = {}
    for output in outputs:
        cohorts.setdefault(output.prediction_event_id, []).append(output)

    comparable = 0
    incomplete = 0
    reason_codes: set[str] = set()
    for prediction_event_id, expected_entries in _entries_by_prediction(plan).items():
        observed = cohorts.get(prediction_event_id, [])
        if {item.policy_id for item in observed} != {item.policy_id for item in expected_entries}:
            incomplete += 1
            reason_codes.add("P9_LIVE_SHADOW_EVIDENCE_INCOMPLETE")
            continue
        hashes = {item.information_set_hash for item in observed}
        if len(hashes) != 1:
            reason_codes.add("P9_LIVE_COMMON_SNAPSHOT_MISMATCH")
            continue
        comparable += 1

    payload = {
        "comparable": comparable,
        "incomplete": incomplete,
        "policies": expected_policy_ids,
        "reason_codes": sorted(reason_codes),
    }
    return ShadowComparabilityReceipt(
        comparable_cohort_count=comparable,
        incomplete_cohort_count=incomplete,
        policy_ids=expected_policy_ids,
        common_snapshot_verified="P9_LIVE_COMMON_SNAPSHOT_MISMATCH" not in reason_codes,
        isolation_verified=True,
        reason_codes=tuple(sorted(reason_codes)),
        receipt_sha256=payload_sha256(payload),
    )


def _entries_by_prediction(plan: ShadowExecutionPlan) -> dict[str, list[ShadowPlanEntry]]:
    grouped: dict[str, list[ShadowPlanEntry]] = {}
    for entry in plan.entries:
        grouped.setdefault(entry.prediction_event_id, []).append(entry)
    return grouped
