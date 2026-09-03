"""P9.S3.M05 — deterministic competition metric registry and replica."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN

from .common import content_sha256
from .errors import MetricPolicyError
from .reason_codes import ReasonCode
from .scoring_models import (
    CompetitionMetricPolicy,
    CompetitionScoreRecord,
    ComponentTransform,
    GoldenMetricExample,
    MetricInputRecord,
    MetricParityCheck,
    MetricParityReport,
    MissingComponentPolicy,
    ScoreComponentRecord,
)


class CompetitionMetricRegistry:
    def __init__(self) -> None:
        self._policies: dict[tuple[str, str], CompetitionMetricPolicy] = {}

    def register(self, policy: CompetitionMetricPolicy) -> None:
        key = (policy.metric_id, policy.metric_version)
        if key in self._policies:
            raise ValueError(f"metric policy already registered: {key}")
        self._policies[key] = policy

    def require(self, metric_id: str, metric_version: str) -> CompetitionMetricPolicy:
        try:
            return self._policies[(metric_id, metric_version)]
        except KeyError as exc:
            raise MetricPolicyError(ReasonCode.METRIC_POLICY_UNKNOWN.value) from exc


def _transform(value: Decimal, component) -> Decimal:
    if component.transform is ComponentTransform.IDENTITY:
        return value
    if component.transform is ComponentTransform.NEGATE:
        return -value
    if component.clip_lower is None or component.clip_upper is None:
        raise MetricPolicyError("clipped competition metric component lacks bounds")
    return min(max(value, component.clip_lower), component.clip_upper)


def compute_competition_score(
    policy: CompetitionMetricPolicy,
    record: MetricInputRecord,
) -> CompetitionScoreRecord:
    values = dict(record.components)
    available = [component for component in policy.components if component.component_id in values]
    missing = [
        component.component_id
        for component in policy.components
        if component.component_id not in values
    ]
    if missing and policy.missing_policy is MissingComponentPolicy.ERROR:
        raise MetricPolicyError(
            f"{ReasonCode.METRIC_INPUT_MISSING.value}: {','.join(sorted(missing))}"
        )
    if not available:
        raise MetricPolicyError(ReasonCode.METRIC_INPUT_MISSING.value)

    weight_scale = Decimal("1")
    if missing and policy.missing_policy is MissingComponentPolicy.OMIT_AND_RENORMALIZE:
        original = sum((abs(component.weight) for component in policy.components), Decimal("0"))
        remaining = sum((abs(component.weight) for component in available), Decimal("0"))
        if remaining == 0:
            raise MetricPolicyError(ReasonCode.METRIC_INPUT_MISSING.value)
        weight_scale = original / remaining

    component_records: list[ScoreComponentRecord] = []
    score = Decimal("0")
    for component in available:
        raw = values[component.component_id]
        transformed = _transform(raw, component)
        effective_weight = component.weight * weight_scale
        contribution = transformed * effective_weight
        score += contribution
        component_records.append(
            ScoreComponentRecord(
                component_id=component.component_id,
                raw_value=raw,
                transformed_value=transformed,
                effective_weight=effective_weight,
                contribution=contribution,
            )
        )

    quantum = Decimal("1").scaleb(-policy.rounding_decimals)
    score = score.quantize(quantum, rounding=ROUND_HALF_EVEN)
    policy_hash = content_sha256(policy)
    body = {
        "metric_id": policy.metric_id,
        "metric_version": policy.metric_version,
        "trial_id": record.trial_id,
        "fold_id": record.fold_id,
        "configuration_id": record.configuration_id,
        "score": score,
        "components": tuple(component_records),
        "observation_count": record.observation_count,
        "policy_sha256": policy_hash,
    }
    return CompetitionScoreRecord(**body, content_sha256=content_sha256(body))


def validate_metric_parity(
    policy: CompetitionMetricPolicy,
    examples: tuple[GoldenMetricExample, ...],
) -> MetricParityReport:
    checks: list[MetricParityCheck] = []
    for example in examples:
        result = compute_competition_score(
            policy,
            MetricInputRecord(
                trial_id=f"golden:{example.example_id}",
                fold_id="golden",
                configuration_id="golden",
                qualification_sha256="0" * 64,
                components=example.inputs,
                observation_count=1,
            ),
        )
        checks.append(
            MetricParityCheck(
                example_id=example.example_id,
                passed=result.score == example.expected_score,
                observed=result.score,
                expected=example.expected_score,
            )
        )
    passed = bool(checks) and all(check.passed for check in checks)
    body = {
        "metric_id": policy.metric_id,
        "metric_version": policy.metric_version,
        "checks": tuple(checks),
        "passed": passed,
    }
    return MetricParityReport(**body, content_sha256=content_sha256(body))
