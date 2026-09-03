"""Ex-ante and explainable person capability profiling for P3.S34.M02."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contracts.artifacts import ArtifactStatus
from ..contracts.capability_artifacts import (
    CapabilityCategory,
    CapabilityLevel,
    CapabilityProfileCoverageReport,
    PersonCapabilityRecord,
    PersonResearchCapabilityPanel,
    PersonResearchResourcePanel,
    PersonResourceRecord,
    ResearchCapabilityTaxonomy,
    ScoreComponent,
)
from ..contracts.capability_configs import CapabilityProfilePolicyConfig
from ..core.errors import fail
from .artifact_construction import finalize, lineage, python_value


def _mapping(value: object) -> Mapping[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        raise fail("P3RT-CONTRACT-3410", "population input must be a mapping")
    return raw


def _records(value: object) -> list[Mapping[str, Any]]:
    raw = _mapping(value)
    rows = raw.get("records", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _population_persons(value: object) -> list[Mapping[str, Any]]:
    raw = _mapping(value)
    manifest = raw.get("population_manifest", raw)
    if isinstance(manifest, Mapping):
        rows = manifest.get("persons", ())
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def _detect_forbidden(value: object, forbidden: set[str], found: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in forbidden:
                found.add(key_text)
            _detect_forbidden(item, forbidden, found)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _detect_forbidden(item, forbidden, found)


def _profile_from_person(person: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = person.get("profile", person)
    return profile if isinstance(profile, Mapping) else person


def _capability_map(profile: Mapping[str, Any]) -> dict[str, float]:
    raw = profile.get("capabilities", {})
    if isinstance(raw, Mapping):
        result: dict[str, float] = {}
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result[str(key)] = min(1.0, max(0.0, float(value)))
        return result
    return {}


def _resource_labels(profile: Mapping[str, Any]) -> tuple[str, ...]:
    raw = profile.get("resources", ())
    labels: set[str] = set()
    if isinstance(raw, Mapping):
        flags = raw.get("flags", ())
        if isinstance(flags, Sequence) and not isinstance(flags, (str, bytes)):
            labels.update(str(item) for item in flags)
        for key, value in raw.items():
            if key == "flags":
                continue
            if isinstance(value, bool) and value:
                labels.add(str(key))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        labels.update(str(item) for item in raw)
    return tuple(sorted(labels))


def _resource_scores(profile: Mapping[str, Any]) -> dict[str, float]:
    raw = profile.get("resources", {})
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[str(key)] = min(1.0, max(0.0, float(value)))
    return result


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(sorted(str(item) for item in value))
    return ()


def _level(score: float, thresholds: Mapping[str, float]) -> CapabilityLevel:
    selected = CapabilityLevel.NONE
    for name in ("NONE", "BASIC", "STANDARD", "ADVANCED", "SPECIALIST"):
        if score >= thresholds[name]:
            selected = CapabilityLevel(name)
    return selected


def _person_index(person_seed_panel: object, validated_population_manifest: object) -> tuple[dict[str, dict[str, Any]], set[str]]:
    index: dict[str, dict[str, Any]] = {}
    expected: set[str] = set()
    for row in _records(person_seed_panel):
        person_id = str(row.get("person_id", ""))
        if not person_id:
            continue
        expected.add(person_id)
        index.setdefault(person_id, {}).update(dict(row))
    for person in _population_persons(validated_population_manifest):
        person_id = str(person.get("person_id", ""))
        if not person_id:
            continue
        expected.add(person_id)
        merged = index.setdefault(person_id, {})
        merged.update(dict(person))
        profile = _profile_from_person(person)
        merged["profile"] = dict(profile)
    return index, expected


def build_person_capability_profiles(
    *,
    person_seed_panel: object,
    validated_population_manifest: object,
    person_schema_policy: object,
    taxonomy: ResearchCapabilityTaxonomy,
    policy: CapabilityProfilePolicyConfig,
    phase3_run_snapshot: object,
) -> tuple[PersonResearchCapabilityPanel, PersonResearchResourcePanel, CapabilityProfileCoverageReport]:
    forbidden = {item.lower() for item in policy.forbidden_source_fields}
    policy_map = _mapping(person_schema_policy)
    forbidden.update(str(item).lower() for item in policy_map.get("forbidden_entitlement_attributes", ()))
    detected: set[str] = set()
    _detect_forbidden(person_seed_panel, forbidden, detected)
    _detect_forbidden(validated_population_manifest, forbidden, detected)
    if detected:
        raise fail(
            "P3RT-AUTH-3411",
            "performance or future-derived fields are forbidden in capability profiling",
            {"fields": sorted(detected)},
        )

    people, expected_ids = _person_index(person_seed_panel, validated_population_manifest)
    definition_by_id = {item.capability_id: item for item in taxonomy.capabilities}
    rule_by_id = {item.capability_id: item for item in policy.capability_rules}
    access_by_id = {item.capability_id: item for item in policy.access_rules}
    resource_rules = {item.resource_id: item for item in policy.resource_rules}
    unknown_rules = sorted((set(rule_by_id) | set(access_by_id)) - set(definition_by_id))
    if unknown_rules:
        raise fail("P3RT-CONTRACT-3412", "profile policy references unknown capability IDs", {"ids": unknown_rules})

    capability_records: list[PersonCapabilityRecord] = []
    resource_records: list[PersonResourceRecord] = []
    missing: list[str] = []
    for person_id in sorted(expected_ids):
        person = people.get(person_id)
        if person is None:
            missing.append(person_id)
            continue
        profile = _profile_from_person(person)
        capabilities = _capability_map(profile)
        resources = _resource_scores(profile)
        resource_labels = set(_resource_labels(profile)) | set(_strings(person.get("resources", ())))
        constraints = set(_strings(person.get("constraints", ())))
        data_classes = set(_strings(person.get("allowed_data_classes", ())))
        role = str(profile.get("economic_role") or person.get("economic_role") or "unknown")
        institution = str(profile.get("institution_type") or person.get("institution") or "")

        for definition in sorted(taxonomy.capabilities, key=lambda item: item.capability_id):
            components: list[ScoreComponent] = []
            score = 0.0
            rule = rule_by_id.get(definition.capability_id)
            access_rule = access_by_id.get(definition.capability_id)
            if rule is not None:
                score = rule.default_score
                components.append(ScoreComponent(
                    component_id="base",
                    source="policy.default_score",
                    source_value=rule.default_score,
                    adjustment=rule.default_score,
                    explanation="Versioned default score from the capability profile policy.",
                ))
                for source_key, weight in sorted(rule.source_capability_weights.items()):
                    source_value = capabilities.get(source_key, 0.0)
                    adjustment = max(-1.0, min(1.0, source_value * weight))
                    score += adjustment
                    components.append(ScoreComponent(
                        component_id=f"source:{source_key}", source=f"capabilities.{source_key}",
                        source_value=source_value, adjustment=adjustment,
                        explanation="Ex-ante source capability contribution.",
                    ))
                for source, table, value in (
                    ("role", rule.role_adjustments, role),
                    ("institution", rule.institution_adjustments, institution),
                ):
                    adjustment = float(table.get(value, 0.0))
                    if adjustment:
                        score += adjustment
                        components.append(ScoreComponent(
                            component_id=f"{source}:{value}", source=source,
                            source_value=value, adjustment=adjustment,
                            explanation=f"Versioned {source} adjustment.",
                        ))
                for label in sorted(resource_labels):
                    adjustment = float(rule.resource_adjustments.get(label, 0.0))
                    if adjustment:
                        score += adjustment
                        components.append(ScoreComponent(
                            component_id=f"resource:{label}", source="resource_label", source_value=label,
                            adjustment=adjustment, explanation="Versioned resource adjustment.",
                        ))
                for label in sorted(constraints):
                    adjustment = float(rule.constraint_adjustments.get(label, 0.0))
                    if adjustment:
                        score += adjustment
                        components.append(ScoreComponent(
                            component_id=f"constraint:{label}", source="constraint", source_value=label,
                            adjustment=adjustment, explanation="Versioned constraint adjustment.",
                        ))
            elif access_rule is not None:
                matched = bool(
                    data_classes.intersection(access_rule.accepted_data_classes)
                    or resource_labels.intersection(access_rule.accepted_resource_labels)
                    or (institution and institution in access_rule.accepted_institutions)
                )
                score = access_rule.score_when_matched if matched else access_rule.default_score
                components.append(ScoreComponent(
                    component_id="access_match", source="access_policy", source_value=matched,
                    adjustment=score, explanation="Resolved from ex-ante data classes, institution, and resources.",
                ))
            elif definition.category is CapabilityCategory.RESOURCE:
                score = resources.get(definition.capability_id, 0.0)
                components.append(ScoreComponent(
                    component_id="resource_score", source=f"resources.{definition.capability_id}",
                    source_value=score, adjustment=score, explanation="Direct normalized resource score.",
                ))
            score = max(0.0, min(1.0, score))
            capability_records.append(PersonCapabilityRecord(
                person_id=person_id,
                capability_id=definition.capability_id,
                category=definition.category,
                score=score,
                level=_level(score, policy.level_thresholds),
                components=tuple(components),
                policy_version=policy.policy_version,
            ))

        for resource_id, rule in sorted(resource_rules.items()):
            direct = max((resources.get(key, 0.0) for key in rule.source_capability_keys), default=0.0)
            matched_labels = tuple(sorted(resource_labels.intersection(rule.accepted_resource_labels)))
            score = max(direct, rule.default_score, 1.0 if matched_labels else 0.0)
            numeric_limit = max((rule.numeric_limit_by_label.get(label, 0.0) for label in matched_labels), default=None)
            resource_records.append(PersonResourceRecord(
                person_id=person_id,
                resource_id=resource_id,
                normalized_score=min(1.0, score),
                numeric_limit=numeric_limit,
                source_labels=matched_labels,
                policy_version=policy.policy_version,
            ))

    expected_count = len(expected_ids)
    profiled_count = expected_count - len(missing)
    coverage = 1.0 if expected_count == 0 else profiled_count / expected_count
    status = ArtifactStatus.READY if coverage >= policy.minimum_population_coverage else ArtifactStatus.DEGRADED
    source_inputs = (
        person_seed_panel, validated_population_manifest, person_schema_policy,
        taxonomy, policy, phase3_run_snapshot,
    )
    capability_panel = finalize(PersonResearchCapabilityPanel, {
        "status": status,
        "lineage": lineage("P3.S34.M02", policy.policy_version, source_inputs),
        "records": tuple(sorted(capability_records, key=lambda item: (item.person_id, item.capability_id))),
        "person_count": profiled_count,
        "capability_count": len(taxonomy.capabilities),
        "reason_codes": () if status is ArtifactStatus.READY else ("P3RT-DATA-3413",),
    })
    resource_panel = finalize(PersonResearchResourcePanel, {
        "status": status,
        "lineage": lineage("P3.S34.M02", policy.policy_version, source_inputs),
        "records": tuple(sorted(resource_records, key=lambda item: (item.person_id, item.resource_id))),
        "reason_codes": () if status is ArtifactStatus.READY else ("P3RT-DATA-3413",),
    })
    report = finalize(CapabilityProfileCoverageReport, {
        "status": status,
        "lineage": lineage("P3.S34.M02", policy.policy_version, source_inputs),
        "expected_person_count": expected_count,
        "profiled_person_count": profiled_count,
        "coverage_ratio": coverage,
        "missing_person_ids": tuple(sorted(missing)),
        "forbidden_source_fields_detected": (),
        "issues": () if status is ArtifactStatus.READY else ("population capability coverage below policy floor",),
        "reason_codes": () if status is ArtifactStatus.READY else ("P3RT-DATA-3413",),
    })
    return capability_panel, resource_panel, report
