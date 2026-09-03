"""P7.S2.M01 — compile policy and decide candidate eligibility."""

from __future__ import annotations

from copy import deepcopy
from pydantic import JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact, verify_artifact_hash
from ..canonical import content_sha256
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from ..s2_errors import P7S2Error
from .common import decision_id, finite_number, get_path, parse_aware_datetime
from .models import (
    CandidateBundleRecord,
    EligibilityCandidateRecord,
    EligibilityDecisionRecord,
    EligibilityPolicy,
    EligibilityPolicyRegistry,
)

MODULE_ID = "P7.S2.M01"

def execute(
    candidate_bundle_payload: dict[str, JsonValue],
    feedback_payload: dict[str, JsonValue],
    registry_payload: dict[str, JsonValue],
    config_payload: dict[str, JsonValue],
) -> dict[str, dict[str, JsonValue]]:
    before = content_sha256(
        {
            "candidate_bundle": candidate_bundle_payload,
            "feedback": feedback_payload,
            "registry": registry_payload,
        }
    )
    config, bundle, feedback, policy = _parse_inputs(
        candidate_bundle_payload,
        feedback_payload,
        registry_payload,
        config_payload,
    )
    effective_policy, applied_adjustments = _apply_feedback(policy, feedback.records)
    try:
        candidate_records = tuple(
            CandidateBundleRecord.model_validate(item).model_dump(mode="json")
            for item in bundle.records
        )
    except ValidationError as exc:
        raise P7S2Error(
            ReasonCode.S2_INPUT_INVALID,
            "temporally safe candidate records failed the S2 boundary schema",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    eligible, blocked, decisions = _evaluate_all(candidate_records, effective_policy)
    outputs = _build_outputs(config, effective_policy, applied_adjustments, eligible, blocked, decisions)
    after = content_sha256(
        {
            "candidate_bundle": candidate_bundle_payload,
            "feedback": feedback_payload,
            "registry": registry_payload,
        }
    )
    if before != after:
        raise P7S2Error(
            ReasonCode.S2_INPUT_MUTATION_DETECTED,
            "eligibility evaluation mutated its inputs",
            MODULE_ID,
        )
    return outputs

def _parse_inputs(candidate_payload, feedback_payload, registry_payload, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        bundle = ArtifactEnvelope.model_validate(candidate_payload)
        feedback = ArtifactEnvelope.model_validate(feedback_payload)
        registry = EligibilityPolicyRegistry.model_validate(registry_payload)
    except ValidationError as exc:
        raise P7S2Error(
            ReasonCode.ELIGIBILITY_POLICY_INVALID,
            "eligibility inputs or policy registry failed validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    _validate_artifact(bundle, "temporally_safe_candidate_bundle")
    _validate_artifact(feedback, "ranking_feedback_context")
    return config, bundle, feedback, registry.active()

def _validate_artifact(artifact: ArtifactEnvelope, expected_name: str) -> None:
    if artifact.artifact_name != expected_name or not verify_artifact_hash(artifact):
        raise P7S2Error(
            ReasonCode.S2_INPUT_INVALID,
            f"{expected_name} is invalid or has a mismatched hash",
            MODULE_ID,
            {"artifact_name": artifact.artifact_name},
        )

def _apply_feedback(
    policy: EligibilityPolicy,
    feedback_records: tuple[dict[str, JsonValue], ...],
) -> tuple[EligibilityPolicy, list[dict[str, JsonValue]]]:
    updates: dict[str, int] = {}
    applied: list[dict[str, JsonValue]] = []
    mutable = set(policy.feedback_mutable_parameters)
    for record in sorted(feedback_records, key=lambda item: str(item.get("feedback_id", ""))):
        adjustments = record.get("adjustments", [])
        if not isinstance(adjustments, list):
            continue
        for adjustment in adjustments:
            if not isinstance(adjustment, dict) or adjustment.get("adjustment_type") != "ELIGIBILITY_THRESHOLD":
                continue
            parameter = adjustment.get("parameter")
            value = adjustment.get("value")
            if parameter not in mutable or parameter in updates:
                raise P7S2Error(
                    ReasonCode.ELIGIBILITY_POLICY_INVALID,
                    "feedback attempts an unauthorized or conflicting eligibility policy change",
                    MODULE_ID,
                    {"parameter": parameter},
                )
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise P7S2Error(
                    ReasonCode.ELIGIBILITY_POLICY_INVALID,
                    "eligibility threshold feedback must be a non-negative integer",
                    MODULE_ID,
                    {"parameter": parameter, "value": value},
                )
            updates[str(parameter)] = value
            applied.append(
                {
                    "feedback_id": record.get("feedback_id"),
                    "parameter": parameter,
                    "value": value,
                }
            )
    effective = policy
    if "min_scenario_count" in updates:
        effective = effective.model_copy(update={"min_scenario_count": updates["min_scenario_count"]})
    if "max_snapshot_age_seconds" in updates:
        effective = effective.model_copy(update={"max_snapshot_age_seconds": updates["max_snapshot_age_seconds"]})
    return effective, applied

def _evaluate_all(records, policy):
    eligible: list[dict[str, JsonValue]] = []
    blocked: list[dict[str, JsonValue]] = []
    decisions: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: str(item.get("candidate_id", ""))):
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
            raise P7S2Error(
                ReasonCode.S2_INPUT_INVALID,
                "candidate bundle must contain unique candidate IDs",
                MODULE_ID,
                {"candidate_id": candidate_id},
            )
        seen.add(candidate_id)
        reasons, evidence = _evaluate_candidate(record, policy)
        status = "BLOCKED" if reasons else "ELIGIBLE"
        decision = EligibilityDecisionRecord(
            decision_id=decision_id(candidate_id, policy.policy_id, status, reasons),
            candidate_id=candidate_id,
            status=status,
            reason_codes=tuple(sorted(reasons)),
            evidence=tuple(evidence),
            policy_id=policy.policy_id,
            policy_version=policy.version,
        ).model_dump(mode="json")
        decorated = deepcopy(record)
        decorated["eligibility_status"] = status
        decorated["eligibility_decision_id"] = decision["decision_id"]
        validated = EligibilityCandidateRecord.model_validate(decorated).model_dump(mode="json")
        (blocked if reasons else eligible).append(validated)
        decisions.append(decision)
    return eligible, blocked, decisions

def _evaluate_candidate(record, policy):
    reasons: list[str] = []
    evidence: list[dict[str, JsonValue]] = []
    _check_sections(record, policy, reasons, evidence)
    _check_objective_and_strategy(record, policy, reasons, evidence)
    _check_required_paths(record, policy, reasons, evidence)
    _check_defined_risk(record, policy, reasons, evidence)
    _check_required_metrics(record, policy, reasons, evidence)
    _check_scenarios(record, policy, reasons, evidence)
    _check_market_scope(record, policy, reasons, evidence)
    _check_snapshot_age(record, policy, reasons, evidence)
    _check_representative(record, policy, reasons, evidence)
    return sorted(set(reasons)), evidence

def _add(reasons, evidence, code: ReasonCode, **details: JsonValue) -> None:
    reasons.append(code.value)
    evidence.append({"reason_code": code.value, **details})

def _check_sections(record, policy, reasons, evidence) -> None:
    for section in policy.required_sections:
        value = record.get(section)
        if value is None or (isinstance(value, list) and not value):
            _add(reasons, evidence, ReasonCode.REQUIRED_METRIC_UNAVAILABLE, path=section)

def _check_objective_and_strategy(record, policy, reasons, evidence) -> None:
    candidate = record.get("candidate", {})
    objective = candidate.get("objective_family") if isinstance(candidate, dict) else None
    strategy = candidate.get("strategy_class") if isinstance(candidate, dict) else None
    if objective not in policy.allowed_objective_families:
        _add(reasons, evidence, ReasonCode.OBJECTIVE_FAMILY_UNSUPPORTED, objective_family=objective)
    if strategy in policy.disabled_strategy_classes:
        _add(reasons, evidence, ReasonCode.STRATEGY_CLASS_DISABLED, strategy_class=strategy)

def _check_required_paths(record, policy, reasons, evidence) -> None:
    for path in policy.required_candidate_paths:
        try:
            value = get_path(record, path)
        except KeyError:
            value = None
        if value is None or value == "":
            _add(reasons, evidence, ReasonCode.REQUIRED_METRIC_UNAVAILABLE, path=path)

def _check_defined_risk(record, policy, reasons, evidence) -> None:
    if not policy.defined_risk_required:
        return
    maximum_loss = finite_number(get_path(record, "risk.maximum_loss", None))
    proven = get_path(record, "risk.maximum_loss_proven", None)
    if maximum_loss is None or maximum_loss < 0:
        _add(reasons, evidence, ReasonCode.DEFINED_RISK_REQUIRED, path="risk.maximum_loss")
    if policy.require_maximum_loss_proven and proven is not True:
        _add(reasons, evidence, ReasonCode.DEFINED_RISK_REQUIRED, path="risk.maximum_loss_proven")

def _check_required_metrics(record, policy, reasons, evidence) -> None:
    objective = get_path(record, "candidate.objective_family", None)
    for path in policy.required_metric_paths_by_objective.get(str(objective), ()):
        value = get_path(record, path, None)
        if finite_number(value) is None:
            _add(reasons, evidence, ReasonCode.REQUIRED_METRIC_UNAVAILABLE, path=path)

def _check_scenarios(record, policy, reasons, evidence) -> None:
    scenarios = record.get("scenario_evaluations")
    count = len(scenarios) if isinstance(scenarios, list) else 0
    if count < policy.min_scenario_count:
        _add(
            reasons,
            evidence,
            ReasonCode.SCENARIO_COVERAGE_INSUFFICIENT,
            scenario_count=count,
            required=policy.min_scenario_count,
        )

def _check_market_scope(record, policy, reasons, evidence) -> None:
    currency = get_path(record, "candidate.currency", None)
    calendar = get_path(record, "market_snapshot.calendar_id", None)
    if policy.allowed_currencies and currency not in policy.allowed_currencies:
        _add(reasons, evidence, ReasonCode.CURRENCY_UNSUPPORTED, currency=currency)
    if calendar is None:
        if policy.require_calendar_id:
            _add(reasons, evidence, ReasonCode.CALENDAR_UNSUPPORTED, calendar_id=None)
    elif policy.allowed_calendars and calendar not in policy.allowed_calendars:
        _add(reasons, evidence, ReasonCode.CALENDAR_UNSUPPORTED, calendar_id=calendar)

def _check_snapshot_age(record, policy, reasons, evidence) -> None:
    try:
        decision = parse_aware_datetime(get_path(record, "candidate.decision_time"))
        snapshot = parse_aware_datetime(get_path(record, "market_snapshot.market_snapshot_time"))
    except (KeyError, TypeError, ValueError):
        _add(reasons, evidence, ReasonCode.MARKET_SNAPSHOT_STALE, reason="timestamp_unavailable")
        return
    age = (decision - snapshot).total_seconds()
    if age < 0 or age > policy.max_snapshot_age_seconds:
        _add(
            reasons,
            evidence,
            ReasonCode.MARKET_SNAPSHOT_STALE,
            age_seconds=age,
            maximum=policy.max_snapshot_age_seconds,
        )

def _check_representative(record, policy, reasons, evidence) -> None:
    if not policy.representative_only:
        return
    candidate_id = record.get("candidate_id")
    rows = record.get("equivalence", [])
    if not isinstance(rows, list):
        return
    representative_ids = {
        row.get("representative_candidate_id")
        for row in rows
        if isinstance(row, dict) and row.get("representative_candidate_id")
    }
    if representative_ids and candidate_id not in representative_ids:
        _add(
            reasons,
            evidence,
            ReasonCode.DUPLICATE_NON_REPRESENTATIVE,
            representative_candidate_ids=sorted(str(item) for item in representative_ids),
        )

def _build_outputs(config, policy, applied_adjustments, eligible, blocked, decisions):
    eligible_artifact = create_artifact(
        artifact_name="eligible_strategy_candidate_panel",
        records=eligible,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
    )
    blocked_artifact = create_artifact(
        artifact_name="eligibility_blocked_candidate_panel",
        records=blocked,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
        capability_status="AVAILABLE" if blocked else "UNAVAILABLE",
    )
    decision_artifact = create_artifact(
        artifact_name="eligibility_decision_panel",
        records=decisions,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
    )
    audit_artifact = create_artifact(
        artifact_name="eligibility_policy_audit",
        records=[
            {
                "status": "PASS",
                "policy_id": policy.policy_id,
                "policy_version": policy.version,
                "candidate_count": len(decisions),
                "eligible_count": len(eligible),
                "blocked_count": len(blocked),
                "applied_feedback_adjustments": applied_adjustments,
            }
        ],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_eligibility_run",
    )
    return {
        "eligible_strategy_candidate_panel": eligible_artifact.model_dump(mode="json"),
        "eligibility_blocked_candidate_panel": blocked_artifact.model_dump(mode="json"),
        "eligibility_decision_panel": decision_artifact.model_dump(mode="json"),
        "eligibility_policy_audit": audit_artifact.model_dump(mode="json"),
    }
