from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .canonical import (
    content_hash,
    ensure_mapping,
    require_fields,
    require_identifier,
    require_non_empty_string,
    require_semver,
    require_unique,
    schema_path_exists,
    stable_sha256,
)
from .errors import S4ContractError

FINANCE_ONLY_OBJECTIVES = frozenset({
    "wealth_growth",
    "capital_preservation",
    "income_generation",
    "forecast_accuracy",
    "liquidity_priority",
})


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise S4ContractError(
            "P3_S4_M02_LIST_INVALID",
            f"{field} must be a non-empty list",
        )
    result = [require_identifier(item, field=field) for item in value]
    require_unique(result, field=field)
    return result


def _path_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise S4ContractError(
            "P3_S4_M02_LIST_INVALID",
            f"{field} must be a non-empty list",
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise S4ContractError(
                "P3_S4_M02_PATH_INVALID",
                f"{field} contains an invalid path",
            )
        components = item.split(".")
        for component in components:
            require_identifier(component, field=field)
        result.append(item)
    require_unique(result, field=field)
    return result




def _validate_tag_registry_integrity(registry: dict[str, Any]) -> None:
    categories = registry.get("categories")
    if not isinstance(categories, list):
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_INTEGRITY_INVALID",
            "tag registry categories are invalid",
        )
    observed_mapping: dict[str, str] = {}
    for category in categories:
        category_id = category.get("category_id")
        for tag in category.get("tags", []):
            observed_mapping[tag.get("tag_id")] = category_id
    if registry.get("category_count") != len(categories):
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_INTEGRITY_INVALID",
            "tag registry category_count does not match content",
        )
    if registry.get("tag_count") != len(observed_mapping):
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_INTEGRITY_INVALID",
            "tag registry tag_count does not match content",
        )
    if registry.get("tag_to_category") != dict(sorted(observed_mapping.items())):
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_INTEGRITY_INVALID",
            "tag registry index does not match categories",
        )
    if registry.get("registry_hash") != content_hash(registry):
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_INTEGRITY_INVALID",
            "tag registry hash does not match content",
        )


def _normalize_taxonomy(raw: dict[str, Any]) -> dict[str, Any]:
    require_fields(
        raw,
        (
            "taxonomy_id",
            "taxonomy_version",
            "principle",
            "role_families",
            "lineage_id",
        ),
        location="economic_role_taxonomy_config",
    )
    if raw["principle"] != "economic_society_not_investor_only":
        raise S4ContractError(
            "P3_S4_M02_TAXONOMY_PRINCIPLE_INVALID",
            "taxonomy must represent the broader economic society",
        )
    families_raw = raw["role_families"]
    if not isinstance(families_raw, list) or len(families_raw) < 3:
        raise S4ContractError(
            "P3_S4_M02_ROLE_FAMILIES_INVALID",
            "at least three role families are required",
        )
    family_ids: list[str] = []
    all_roles: list[str] = []
    families: list[dict[str, Any]] = []
    role_to_family: dict[str, str] = {}
    for index, family_raw in enumerate(families_raw):
        family = ensure_mapping(family_raw, f"role_families[{index}]")
        require_fields(
            family,
            ("family_id", "roles"),
            location=f"role_families[{index}]",
        )
        family_id = require_identifier(
            family["family_id"],
            field=f"role_families[{index}].family_id",
        )
        roles = _string_list(
            family["roles"],
            f"role_families[{index}].roles",
        )
        family_ids.append(family_id)
        all_roles.extend(roles)
        for role in roles:
            role_to_family[role] = family_id
        families.append({
            "family_id": family_id,
            "roles": sorted(roles),
        })
    require_unique(family_ids, field="role family")
    require_unique(all_roles, field="economic role")
    if set(family_ids) == {"market_participants"}:
        raise S4ContractError(
            "P3_S4_M02_FINANCE_ONLY_TAXONOMY",
            "taxonomy cannot be investor-only",
        )
    families.sort(key=lambda item: item["family_id"])
    return {
        "taxonomy_id": require_non_empty_string(
            raw["taxonomy_id"],
            field="taxonomy_id",
        ),
        "taxonomy_version": require_semver(
            raw["taxonomy_version"],
            field="taxonomy_version",
        ),
        "principle": raw["principle"],
        "families": families,
        "role_to_family": dict(sorted(role_to_family.items())),
        "family_count": len(family_ids),
        "role_count": len(all_roles),
        "lineage_id": require_non_empty_string(
            raw["lineage_id"],
            field="taxonomy.lineage_id",
        ),
    }


def _normalize_objectives(
    raw: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    require_fields(
        raw,
        (
            "registry_id",
            "registry_version",
            "objective_dimensions",
            "family_defaults",
            "weight_policy",
            "lineage_id",
        ),
        location="role_objective_registry_config",
    )
    dimensions = _string_list(
        raw["objective_dimensions"],
        "objective_dimensions",
    )
    defaults_raw = ensure_mapping(
        raw["family_defaults"],
        "family_defaults",
    )
    family_ids = {
        item["family_id"]
        for item in taxonomy["families"]
    }
    if set(defaults_raw) != family_ids:
        raise S4ContractError(
            "P3_S4_M02_FAMILY_DEFAULTS_MISMATCH",
            "objective defaults must cover every role family exactly",
        )
    family_defaults: dict[str, list[str]] = {}
    for family_id in sorted(family_ids):
        objectives = _string_list(
            defaults_raw[family_id],
            f"family_defaults.{family_id}",
        )
        unknown = sorted(set(objectives) - set(dimensions))
        if unknown:
            raise S4ContractError(
                "P3_S4_M02_UNKNOWN_OBJECTIVE",
                f"{family_id} uses unknown objectives: {unknown}",
            )
        if (
            family_id != "market_participants"
            and set(objectives) <= FINANCE_ONLY_OBJECTIVES
        ):
            raise S4ContractError(
                "P3_S4_M02_FINANCE_ONLY_OBJECTIVES",
                f"{family_id} requires a non-financial objective",
            )
        family_defaults[family_id] = sorted(objectives)
    weight_policy = ensure_mapping(
        raw["weight_policy"],
        "weight_policy",
    )
    require_fields(
        weight_policy,
        ("normalization", "sum_tolerance", "minimum", "maximum"),
        location="weight_policy",
    )
    if weight_policy["normalization"] != "sum_to_one":
        raise S4ContractError(
            "P3_S4_M02_WEIGHT_POLICY_INVALID",
            "objective weights must sum to one",
        )
    tolerance = weight_policy["sum_tolerance"]
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not 0 < float(tolerance) <= 1e-3
    ):
        raise S4ContractError(
            "P3_S4_M02_WEIGHT_POLICY_INVALID",
            "sum_tolerance must be in (0, 1e-3]",
        )
    if weight_policy["minimum"] != 0 or weight_policy["maximum"] != 1:
        raise S4ContractError(
            "P3_S4_M02_WEIGHT_POLICY_INVALID",
            "objective weights must use [0, 1]",
        )
    role_defaults = {
        role: list(family_defaults[family_id])
        for role, family_id in taxonomy["role_to_family"].items()
    }
    return {
        "registry_id": require_non_empty_string(
            raw["registry_id"],
            field="objective_registry_id",
        ),
        "registry_version": require_semver(
            raw["registry_version"],
            field="objective_registry_version",
        ),
        "dimensions": sorted(dimensions),
        "family_defaults": family_defaults,
        "role_defaults": dict(sorted(role_defaults.items())),
        "weight_policy": {
            "normalization": "sum_to_one",
            "sum_tolerance": float(tolerance),
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "lineage_id": require_non_empty_string(
            raw["lineage_id"],
            field="objectives.lineage_id",
        ),
    }


def _normalize_representation(
    raw: dict[str, Any],
    taxonomy: dict[str, Any],
) -> dict[str, Any]:
    require_fields(
        raw,
        (
            "config_id",
            "config_version",
            "weight_field",
            "sum_tolerance",
            "target_role_family_shares",
            "max_single_person_weight",
            "min_effective_population",
            "lineage_id",
        ),
        location="population_representation_config",
    )
    if raw["weight_field"] != "representation_weight":
        raise S4ContractError(
            "P3_S4_M02_WEIGHT_FIELD_INVALID",
            "weight field must be representation_weight",
        )
    tolerance = raw["sum_tolerance"]
    if (
        not isinstance(tolerance, (int, float))
        or isinstance(tolerance, bool)
        or not 0 < float(tolerance) <= 1e-3
    ):
        raise S4ContractError(
            "P3_S4_M02_REPRESENTATION_TOLERANCE_INVALID",
            "sum_tolerance must be in (0, 1e-3]",
        )
    shares = ensure_mapping(
        raw["target_role_family_shares"],
        "target_role_family_shares",
    )
    family_ids = {
        item["family_id"]
        for item in taxonomy["families"]
    }
    if set(shares) != family_ids:
        raise S4ContractError(
            "P3_S4_M02_ROLE_SHARE_KEYS_MISMATCH",
            "representation shares must cover every family exactly",
        )
    normalized_shares: dict[str, float] = {}
    for family_id, value in shares.items():
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 < float(value) <= 1
        ):
            raise S4ContractError(
                "P3_S4_M02_ROLE_SHARE_INVALID",
                f"invalid share for {family_id}",
            )
        normalized_shares[family_id] = float(value)
    if abs(sum(normalized_shares.values()) - 1.0) > float(tolerance):
        raise S4ContractError(
            "P3_S4_M02_ROLE_SHARE_SUM_INVALID",
            "role-family shares must sum to one",
        )
    max_weight = raw["max_single_person_weight"]
    if (
        not isinstance(max_weight, (int, float))
        or isinstance(max_weight, bool)
        or not 0 < float(max_weight) <= 1
    ):
        raise S4ContractError(
            "P3_S4_M02_MAX_PERSON_WEIGHT_INVALID",
            "max_single_person_weight must be in (0, 1]",
        )
    minimum_population = raw["min_effective_population"]
    if (
        not isinstance(minimum_population, int)
        or isinstance(minimum_population, bool)
        or minimum_population < 2
    ):
        raise S4ContractError(
            "P3_S4_M02_EFFECTIVE_POPULATION_INVALID",
            "min_effective_population must be an integer >= 2",
        )
    return {
        "config_id": require_non_empty_string(
            raw["config_id"],
            field="representation.config_id",
        ),
        "config_version": require_semver(
            raw["config_version"],
            field="representation.config_version",
        ),
        "weight_field": "representation_weight",
        "sum_tolerance": float(tolerance),
        "target_role_family_shares": dict(
            sorted(normalized_shares.items())
        ),
        "max_single_person_weight": float(max_weight),
        "min_effective_population": minimum_population,
        "lineage_id": require_non_empty_string(
            raw["lineage_id"],
            field="representation.lineage_id",
        ),
    }


def _validate_person_schema(
    schema: dict[str, Any],
    policy: dict[str, Any],
    taxonomy: dict[str, Any],
    objectives: dict[str, Any],
) -> dict[str, Any]:
    Draft202012Validator.check_schema(schema)
    required = set(schema.get("required", []))
    expected = {
        "person_id",
        "representation_weight",
        "identity",
        "resources",
        "cognitive_capabilities",
        "decision_profile",
        "objective_weights",
        "tags",
        "creator_provenance",
        "lineage_id",
    }
    missing = sorted(expected - required)
    if missing:
        raise S4ContractError(
            "P3_S4_M02_PERSON_SCHEMA_REQUIRED_FIELDS_MISSING",
            f"person schema missing required fields: {missing}",
        )
    for path in policy["immutable_fields"] + policy["state_speed_classes"]["slow"]:
        if not schema_path_exists(schema, path):
            raise S4ContractError(
                "P3_S4_M02_STATE_PATH_UNKNOWN",
                f"person profile does not contain {path}",
            )
    identity = schema.get("properties", {}).get("identity", {})
    identity_properties = identity.get("properties", {})
    role_enum = set(
        identity_properties.get("economic_role", {}).get("enum", [])
    )
    family_enum = set(
        identity_properties
        .get("economic_role_family", {})
        .get("enum", [])
    )
    expected_roles = set(taxonomy["role_to_family"])
    expected_families = {
        item["family_id"]
        for item in taxonomy["families"]
    }
    if role_enum != expected_roles:
        raise S4ContractError(
            "P3_S4_M02_PERSON_SCHEMA_ROLE_ENUM_MISMATCH",
            "person schema role enum differs from taxonomy",
        )
    if family_enum != expected_families:
        raise S4ContractError(
            "P3_S4_M02_PERSON_SCHEMA_FAMILY_ENUM_MISMATCH",
            "person schema family enum differs from taxonomy",
        )
    objective_schema = schema.get("properties", {}).get(
        "objective_weights",
        {},
    )
    objective_enum = set(
        objective_schema.get("propertyNames", {}).get("enum", [])
    )
    if objective_enum != set(objectives["dimensions"]):
        raise S4ContractError(
            "P3_S4_M02_PERSON_SCHEMA_OBJECTIVE_ENUM_MISMATCH",
            "person schema objective enum differs from registry",
        )
    schema_id = require_non_empty_string(
        schema.get("$id", "person_profile.v1"),
        field="person_profile_schema.$id",
    )
    schema_version = require_semver(
        schema.get("artifact_schema_version", schema.get("schema_version", "1.0.0")),
        field="person_profile_schema.artifact_schema_version",
    )
    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "content_hash": stable_sha256(schema),
    }


