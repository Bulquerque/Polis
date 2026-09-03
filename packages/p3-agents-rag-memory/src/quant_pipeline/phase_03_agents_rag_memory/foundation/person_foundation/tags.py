from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from .canonical import (
    content_hash,
    ensure_mapping,
    require_fields,
    require_identifier,
    require_no_forbidden_fields,
    require_no_secrets,
    require_non_empty_string,
    require_semver,
    require_unique,
)
from .errors import Issue, S4ContractError
from .schemas import SchemaRegistry, package_root

LOGGER = logging.getLogger(__name__)
REQUIRED_INPUTS = ("personality_tag_registry_config",)


def _range_contract(value: Any, field: str) -> dict[str, float]:
    mapping = ensure_mapping(value, field)
    require_fields(mapping, ("minimum", "maximum"), location=field)
    minimum = mapping["minimum"]
    maximum = mapping["maximum"]
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool):
        raise S4ContractError(
            "P3_S4_M01_ASSIGNMENT_RANGE_INVALID",
            f"{field}.minimum must be numeric",
        )
    if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
        raise S4ContractError(
            "P3_S4_M01_ASSIGNMENT_RANGE_INVALID",
            f"{field}.maximum must be numeric",
        )
    if float(minimum) != 0.0 or float(maximum) != 1.0:
        raise S4ContractError(
            "P3_S4_M01_ASSIGNMENT_RANGE_INVALID",
            f"{field} must use the closed interval [0, 1]",
        )
    return {"minimum": 0.0, "maximum": 1.0}



def _normalize_aliases(raw_aliases: object, *, category_id: str, tag_id: str) -> list[str]:
    if not isinstance(raw_aliases, list):
        raise S4ContractError(
            "P3_S4_M01_ALIASES_INVALID",
            f"aliases for {tag_id} must be a list",
        )
    aliases = [
        require_identifier(alias, field=f"{category_id}.{tag_id}.aliases")
        for alias in raw_aliases
    ]
    require_unique(aliases, field=f"aliases for {tag_id}")
    return sorted(aliases)


def _normalize_tag(raw_tag: object, *, category_id: str, tag_index: int) -> dict[str, Any]:
    location = f"{category_id}.tags[{tag_index}]"
    tag = ensure_mapping(raw_tag, location)
    require_fields(tag, ("tag_id", "description"), location=location)
    tag_id = require_identifier(tag["tag_id"], field=f"{location}.tag_id")
    description = require_non_empty_string(
        tag["description"], field=f"{category_id}.{tag_id}.description"
    )
    status = tag.get("status", "ACTIVE")
    if status not in {"ACTIVE", "DEPRECATED"}:
        raise S4ContractError(
            "P3_S4_M01_TAG_STATUS_INVALID", f"invalid status for tag {tag_id}"
        )
    return {
        "tag_id": tag_id,
        "description": description,
        "status": status,
        "aliases": _normalize_aliases(
            tag.get("aliases", []), category_id=category_id, tag_id=tag_id
        ),
    }


def _normalize_category(raw_category: object, *, category_index: int) -> dict[str, Any]:
    location = f"categories[{category_index}]"
    category = ensure_mapping(raw_category, location)
    require_fields(category, ("category_id", "tags"), location=location)
    category_id = require_identifier(category["category_id"], field=f"{location}.category_id")
    raw_tags = category["tags"]
    if not isinstance(raw_tags, list) or not raw_tags:
        raise S4ContractError(
            "P3_S4_M01_TAGS_INVALID", f"category {category_id} requires at least one tag"
        )
    tags = [_normalize_tag(item, category_id=category_id, tag_index=i) for i, item in enumerate(raw_tags)]
    return {"category_id": category_id, "tags": sorted(tags, key=lambda item: item["tag_id"])}


def _normalize_categories(raw_categories: object) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(raw_categories, list) or not raw_categories:
        raise S4ContractError(
            "P3_S4_M01_CATEGORIES_INVALID", "categories must be a non-empty list"
        )
    categories = [_normalize_category(item, category_index=i) for i, item in enumerate(raw_categories)]
    category_ids = [item["category_id"] for item in categories]
    tag_ids = [tag["tag_id"] for category in categories for tag in category["tags"]]
    aliases = [alias for category in categories for tag in category["tags"] for alias in tag["aliases"]]
    require_unique(category_ids, field="category_id")
    require_unique(tag_ids, field="tag_id")
    require_unique(aliases, field="tag aliases")
    collisions = sorted(set(tag_ids) & set(aliases))
    if collisions:
        raise S4ContractError(
            "P3_S4_M01_ALIAS_COLLISION", f"aliases collide with tag IDs: {collisions}"
        )
    categories.sort(key=lambda item: item["category_id"] )
    return categories, tag_ids

def load_personality_tag_registry(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate the canonical, versioned personality-tag vocabulary."""
    del config
    LOGGER.info("module_started", extra={"module_id": "P3.S4.M01"})
    values = ensure_mapping(inputs, "inputs")
    if set(values) != set(REQUIRED_INPUTS):
        raise S4ContractError(
            "P3_S4_M01_INPUT_SET_INVALID",
            f"expected {REQUIRED_INPUTS}, observed {sorted(values)}",
        )
    raw = ensure_mapping(values["personality_tag_registry_config"], "personality_tag_registry_config")
    require_no_forbidden_fields(raw, "personality_tag_registry_config")
    require_no_secrets(raw, "personality_tag_registry_config")
    require_fields(
        raw,
        ("registry_id", "registry_version", "policy", "assignment_contract", "categories", "lineage_id"),
        location="personality_tag_registry_config",
    )
    if raw["policy"] != "fixed_registry_no_free_tag_creation":
        raise S4ContractError(
            "P3_S4_M01_POLICY_INVALID",
            "tag registry must forbid free runtime tag creation",
        )
    assignment = ensure_mapping(raw["assignment_contract"], "assignment_contract")
    if set(assignment) != {"intensity", "confidence"}:
        raise S4ContractError(
            "P3_S4_M01_ASSIGNMENT_FIELDS_INVALID",
            "assignment contract must contain intensity and confidence",
        )
    categories, tag_ids = _normalize_categories(raw["categories"] )
    active_aliases = [
        alias
        for category in categories
        for tag in category["tags"]
        for alias in tag.get("aliases", ())
    ]
    if active_aliases:
        raise S4ContractError(
            "P3_S4_M01_ACTIVE_ALIAS_FORBIDDEN",
            "Active ontology aliases are forbidden; use the migration-only alias registry",
        )
    tag_to_category = {
        tag["tag_id"]: category["category_id"]
        for category in categories
        for tag in category["tags"]
    }
    output: dict[str, Any] = {
        "schema_id": "personality_tag_registry.v2",
        "schema_version": "2.0.0",
        "contract_version": "p3.s4.tag-registry.v2",
        "registry_id": require_non_empty_string(raw["registry_id"], field="registry_id"),
        "registry_version": require_semver(raw["registry_version"], field="registry_version"),
        "policy": "fixed_registry_no_free_tag_creation",
        "assignment_contract": {
            "intensity": _range_contract(assignment["intensity"], "assignment_contract.intensity"),
            "confidence": _range_contract(assignment["confidence"], "assignment_contract.confidence"),
        },
        "categories": categories,
        "tag_to_category": dict(sorted(tag_to_category.items())),
        "category_count": len(categories),
        "tag_count": len(tag_ids),
        "lineage_id": require_non_empty_string(raw["lineage_id"], field="lineage_id"),
        "status": "READY",
        "issues": [],
    }
    output["registry_hash"] = content_hash(output)
    SchemaRegistry(package_root()).validate(
        "schemas/personality_tag_registry.schema.yaml", output, label="personality_tag_registry"
    )
    LOGGER.info(
        "module_succeeded",
        extra={
            "module_id": "P3.S4.M01",
            "category_count": output["category_count"],
            "tag_count": output["tag_count"],
        },
    )
    return output


def validate_tag_assignments(
    assignments: list[dict[str, Any]],
    registry: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    known = set(registry.get("tag_to_category", {}))
    alias_to_tag = {
        alias: tag["tag_id"]
        for category in registry.get("categories", ())
        for tag in category.get("tags", ())
        for alias in tag.get("aliases", ())
    }
    if not isinstance(assignments, list):
        raise S4ContractError(
            "P3_S4_M01_ASSIGNMENTS_INVALID",
            "assignments must be a list",
        )
    normalized: list[dict[str, Any]] = []
    seen: list[str] = []
    for index, raw in enumerate(assignments):
        assignment = ensure_mapping(raw, f"assignments[{index}]")
        require_fields(
            assignment,
            ("tag_id", "intensity", "confidence"),
            location=f"assignments[{index}]",
        )
        observed_tag_id = require_identifier(
            assignment["tag_id"],
            field=f"assignments[{index}].tag_id",
        )
        tag_id = alias_to_tag.get(observed_tag_id, observed_tag_id)
        if tag_id not in known:
            raise S4ContractError(
                "P3_S4_M01_UNREGISTERED_TAG",
                f"unknown tag: {observed_tag_id}",
            )
        for field in ("intensity", "confidence"):
            value = assignment[field]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= float(value) <= 1
            ):
                raise S4ContractError(
                    "P3_S4_M01_ASSIGNMENT_VALUE_INVALID",
                    f"{field} for {tag_id} must be in [0, 1]",
                )
        seen.append(tag_id)
        normalized.append({
            "tag_id": tag_id,
            "intensity": float(assignment["intensity"]),
            "confidence": float(assignment["confidence"]),
        })
    require_unique(seen, field="assigned tag_id")
    return tuple(sorted(normalized, key=lambda item: item["tag_id"]))
