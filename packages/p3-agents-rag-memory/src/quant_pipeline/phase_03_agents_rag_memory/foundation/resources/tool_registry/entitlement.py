from __future__ import annotations

from collections.abc import Iterable

from .canonical import content_hash
from .errors import ContractError, ErrorCategory, PolicyError, error
from .models import (
    ArtifactStatus,
    AvailabilityStatus,
    DecisionEffect,
    EffectiveTool,
    EntitlementAction,
    EntitlementBudget,
    EntitlementCoverage,
    EntitlementDecision,
    EntitlementRecord,
    EntitlementRule,
    PersonSchemaPolicy,
    PersonSeed,
    PersonSeedPanel,
    PersonToolEntitlementPanel,
    RuleBudget,
    ToolEntitlementConfig,
    ToolRegistryArtifact,
)

_FORBIDDEN_FRAGMENTS = {
    "performance",
    "return",
    "future",
    "candidate_score",
    "rank_score",
    "portfolio",
    "trade_decision",
    "buy_sell",
    "profit",
    "pnl",
}


def _recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).casefold())
            keys.update(_recursive_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_recursive_keys(item))
    return keys


def validate_entitlement_config(
    config: ToolEntitlementConfig,
    policy: PersonSchemaPolicy,
) -> None:
    keys = _recursive_keys(config.model_dump(mode="python"))
    forbidden = {
        key
        for key in keys
        if any(fragment in key for fragment in (*_FORBIDDEN_FRAGMENTS, *policy.forbidden_entitlement_attributes))
    }
    # Configuration declaration keys are allowed; actual rule selectors are not.
    forbidden.discard("performance_based_entitlement_forbidden")
    if forbidden:
        raise PolicyError(
            error(
                "P3_S15_M02_PERFORMANCE_ATTRIBUTE_FORBIDDEN",
                ErrorCategory.POLICY,
                "entitlement configuration references forbidden performance/future attributes",
                fields=sorted(forbidden),
            )
        )
    rule_ids = [rule.rule_id for rule in config.rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ContractError(
            error(
                "P3_S15_M02_DUPLICATE_RULE_ID",
                ErrorCategory.CONTRACT,
                "entitlement rule IDs must be unique",
            )
        )


def validate_persons(panel: PersonSeedPanel, policy: PersonSchemaPolicy) -> None:
    ids = [person.person_id for person in panel.records]
    if len(ids) != len(set(ids)):
        raise ContractError(
            error(
                "P3_S15_M02_DUPLICATE_PERSON_ID",
                ErrorCategory.CONTRACT,
                "person IDs must be unique",
            )
        )
    allowed_roles = set(policy.allowed_roles)
    allowed_resources = set(policy.allowed_resources)
    allowed_capabilities = set(policy.allowed_capabilities)
    allowed_constraints = set(policy.allowed_constraints)
    for person in panel.records:
        if person.economic_role not in allowed_roles:
            raise ContractError(
                error(
                    "P3_S15_M02_ROLE_UNKNOWN",
                    ErrorCategory.CONTRACT,
                    "person economic_role is absent from person_schema_policy",
                    person_id=person.person_id,
                    role=person.economic_role,
                )
            )
        unknown_resources = set(person.resources) - allowed_resources
        unknown_capabilities = set(person.capabilities) - allowed_capabilities
        unknown_constraints = set(person.constraints) - allowed_constraints
        if unknown_resources or unknown_capabilities or unknown_constraints:
            raise ContractError(
                error(
                    "P3_S15_M02_PERSON_ATTRIBUTE_UNKNOWN",
                    ErrorCategory.CONTRACT,
                    "person contains attributes outside person_schema_policy",
                    person_id=person.person_id,
                    unknown_resources=sorted(unknown_resources),
                    unknown_capabilities=sorted(unknown_capabilities),
                    unknown_constraints=sorted(unknown_constraints),
                )
            )


def _subject_matches(rule: EntitlementRule, person: PersonSeed) -> bool:
    subject = rule.subject
    if subject.roles and person.economic_role not in subject.roles:
        return False
    if subject.institutions and person.institution not in subject.institutions:
        return False
    if not set(subject.required_resources).issubset(person.resources):
        return False
    if not set(subject.required_constraints).issubset(person.constraints):
        return False
    if set(subject.forbidden_constraints).intersection(person.constraints):
        return False
    for capability, minimum in subject.minimum_capabilities.items():
        if person.capabilities.get(capability, 0.0) < minimum:
            return False
    return True


def _resource_matches(rule: EntitlementRule, tool: EffectiveTool) -> bool:
    resource = rule.resource
    if resource.tool_ids and tool.tool_id not in resource.tool_ids:
        return False
    if resource.capability_families and tool.capability_family not in resource.capability_families:
        return False
    if resource.execution_modes and tool.execution_mode not in resource.execution_modes:
        return False
    if resource.sensitivity_classes and tool.sensitivity_class not in resource.sensitivity_classes:
        return False
    if resource.required_data_classes and not set(resource.required_data_classes).issubset(
        tool.permitted_data_classes
    ):
        return False
    return True


def _person_data_access_matches(rule: EntitlementRule, person: PersonSeed) -> bool:
    required = set(rule.resource.required_data_classes)
    return required.issubset(person.allowed_data_classes)


def _min_optional(values: Iterable[float | int | None]) -> float | int | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _build_budget(
    *,
    config: ToolEntitlementConfig,
    tool: EffectiveTool,
    allow_rules: tuple[EntitlementRule, ...],
) -> EntitlementBudget:
    rule_calls = [rule.budget.max_calls_per_cycle for rule in allow_rules]
    calls = int(
        _min_optional(
            (
                config.default_budget_calls_per_cycle,
                config.maximum_entitlement_calls_per_cycle,
                tool.max_calls_per_person_cycle,
                *rule_calls,
            )
        )
        or 0
    )
    costs = [rule.budget.max_cost_per_cycle for rule in allow_rules]
    latencies = [rule.budget.max_latency_ms for rule in allow_rules]
    max_cost = _min_optional((config.default_max_cost_per_cycle, *costs))
    max_latency = _min_optional((config.default_max_latency_ms, tool.timeout_policy.timeout_ms, *latencies))
    return EntitlementBudget(
        max_calls_per_cycle=calls,
        max_cost_per_cycle=float(max_cost) if max_cost is not None else None,
        max_latency_ms=int(max_latency) if max_latency is not None else None,
    )


def evaluate_pair(
    *,
    person: PersonSeed,
    tool: EffectiveTool,
    config: ToolEntitlementConfig,
) -> EntitlementRecord:
    empty_budget = EntitlementBudget(max_calls_per_cycle=0)
    if tool.availability_status != AvailabilityStatus.AVAILABLE_QUALIFIED:
        return EntitlementRecord(
            person_id=person.person_id,
            tool_id=tool.tool_id,
            decision=EntitlementDecision.TOOL_UNAVAILABLE,
            allowed_actions=(),
            budget=empty_budget,
            allowed_operations=(),
            allowed_data_classes=(),
            reason_codes=("TOOL_NOT_AVAILABLE_QUALIFIED", *tool.reason_codes),
            policy_version=config.schema_version,
        )

    matching = tuple(
        sorted(
            (
                rule
                for rule in config.rules
                if _subject_matches(rule, person)
                and _resource_matches(rule, tool)
                and _person_data_access_matches(rule, person)
            ),
            key=lambda rule: (-rule.priority, rule.rule_id),
        )
    )
    deny_rules = tuple(rule for rule in matching if rule.effect == DecisionEffect.DENY)
    allow_rules = tuple(rule for rule in matching if rule.effect == DecisionEffect.ALLOW)
    if deny_rules:
        return EntitlementRecord(
            person_id=person.person_id,
            tool_id=tool.tool_id,
            decision=EntitlementDecision.DENIED,
            allowed_actions=(),
            budget=empty_budget,
            matched_deny_rule_ids=tuple(rule.rule_id for rule in deny_rules),
            reason_codes=tuple(rule.reason_code for rule in deny_rules),
            policy_version=config.schema_version,
        )
    if not allow_rules:
        return EntitlementRecord(
            person_id=person.person_id,
            tool_id=tool.tool_id,
            decision=EntitlementDecision.DENIED,
            allowed_actions=(),
            budget=empty_budget,
            reason_codes=("DEFAULT_DENY_NO_ALLOW_RULE",),
            policy_version=config.schema_version,
        )

    actions = tuple(sorted({action for rule in allow_rules for action in rule.actions}, key=lambda x: x.value))
    if EntitlementAction.REQUEST not in actions:
        # Discovery-only access remains denied for invocation but is still useful to S20.
        decision = EntitlementDecision.ALLOWED if actions else EntitlementDecision.DENIED
    else:
        decision = EntitlementDecision.ALLOWED
    budget = _build_budget(config=config, tool=tool, allow_rules=allow_rules)
    if budget.max_calls_per_cycle == 0:
        decision = EntitlementDecision.DENIED
        actions = ()
        reason_codes = ("EFFECTIVE_BUDGET_ZERO",)
    else:
        reason_codes = tuple(rule.reason_code for rule in allow_rules)
    allowed_data = tuple(sorted(set(person.allowed_data_classes).intersection(tool.permitted_data_classes)))
    return EntitlementRecord(
        person_id=person.person_id,
        tool_id=tool.tool_id,
        decision=decision,
        allowed_actions=actions,
        budget=budget,
        allowed_operations=tuple(action.value for action in actions),
        allowed_data_classes=allowed_data,
        matched_allow_rule_ids=tuple(rule.rule_id for rule in allow_rules),
        reason_codes=reason_codes,
        policy_version=config.schema_version,
    )


def build_entitlement_panel(
    *,
    registry: ToolRegistryArtifact,
    persons: PersonSeedPanel,
    person_schema_policy: PersonSchemaPolicy,
    config: ToolEntitlementConfig,
) -> PersonToolEntitlementPanel:
    validate_entitlement_config(config, person_schema_policy)
    validate_persons(persons, person_schema_policy)
    records = tuple(
        evaluate_pair(person=person, tool=tool, config=config)
        for person in sorted(persons.records, key=lambda item: item.person_id)
        for tool in sorted(registry.tools, key=lambda item: item.tool_id)
    )
    allowed = sum(record.decision == EntitlementDecision.ALLOWED for record in records)
    unavailable = sum(record.decision == EntitlementDecision.TOOL_UNAVAILABLE for record in records)
    denied = len(records) - allowed - unavailable
    if not registry.tools:
        status = ArtifactStatus.EMPTY
        issues = ("NO_TOOLS_AVAILABLE",)
    elif not persons.records:
        status = ArtifactStatus.EMPTY
        issues = ("EMPTY_POPULATION",)
    else:
        status = ArtifactStatus.READY
        issues = ()
    coverage = EntitlementCoverage(
        person_count=len(persons.records),
        tool_count=len(registry.tools),
        evaluated_pair_count=len(records),
        allowed_pair_count=allowed,
        denied_pair_count=denied,
        unavailable_tool_pair_count=unavailable,
    )
    base = {
        "artifact_name": "person_tool_entitlement_panel",
        "schema_id": "person_tool_entitlement_panel.v2",
        "schema_version": "2.0.0",
        "run_id": registry.run_id,
        "cycle_id": registry.cycle_id,
        "snapshot_id": registry.snapshot_id,
        "as_of_time": registry.as_of_time,
        "lineage_id": f"{registry.lineage_id}:{persons.lineage_id}",
        "status": status,
        "grain": ("person_id", "tool_id"),
        "primary_key": ("person_id", "tool_id"),
        "tool_registry_hash": registry.content_hash,
        "person_seed_panel_hash": content_hash(persons),
        "person_schema_policy_hash": content_hash(person_schema_policy),
        "entitlement_config_hash": content_hash(config),
        "records": records,
        "coverage": coverage,
        "issues": issues,
    }
    from .canonical import compute_artifact_hash

    digest = compute_artifact_hash(base)
    return PersonToolEntitlementPanel(
        artifact_id=f"entitlements_{digest[:24]}",
        content_hash=digest,
        **base,
    )
