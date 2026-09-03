from __future__ import annotations

import logging
from typing import Any

from .canonical import (
    content_hash,
    ensure_mapping,
    require_fields,
    require_no_forbidden_fields,
    require_no_secrets,
    require_non_empty_string,
    require_semver,
)
from .errors import S4ContractError
from .registries import (
    _normalize_objectives,
    _normalize_representation,
    _normalize_taxonomy,
    _path_list,
    _string_list,
    _validate_person_schema,
    _validate_tag_registry_integrity,
)
from .schemas import (
    SchemaRegistry,
    package_root,
    resolve_schema_document,
)

LOGGER = logging.getLogger(__name__)
REQUIRED_INPUTS = (
    "person_schema_policy_config",
    "personality_tag_registry",
    "economic_role_taxonomy_config",
    "role_objective_registry_config",
    "population_representation_config",
)


def load_person_schema_policy(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    LOGGER.info("module_started", extra={"module_id": "P3.S4.M02"})
    values = ensure_mapping(inputs, "inputs")
    if set(values) != set(REQUIRED_INPUTS):
        raise S4ContractError(
            "P3_S4_M02_INPUT_SET_INVALID",
            f"expected {REQUIRED_INPUTS}, observed {sorted(values)}",
        )
    for name, value in values.items():
        require_no_forbidden_fields(value, name)
        require_no_secrets(value, name)

    policy = ensure_mapping(
        values["person_schema_policy_config"],
        "person_schema_policy_config",
    )
    require_fields(
        policy,
        (
            "policy_id",
            "policy_version",
            "schema",
            "immutable_fields",
            "state_speed_classes",
            "state_class_locations",
            "objective_weight_policy",
            "consistency_rule_ids",
            "lineage_id",
        ),
        location="person_schema_policy_config",
    )
    tag_registry = ensure_mapping(
        values["personality_tag_registry"],
        "personality_tag_registry",
    )
    SchemaRegistry(package_root()).validate(
        "schemas/personality_tag_registry.schema.yaml",
        tag_registry,
        label="personality_tag_registry",
    )
    if tag_registry.get("status") != "READY":
        raise S4ContractError(
            "P3_S4_M02_TAG_REGISTRY_NOT_READY",
            "tag registry must be READY",
        )
    _validate_tag_registry_integrity(tag_registry)
    taxonomy = _normalize_taxonomy(
        ensure_mapping(
            values["economic_role_taxonomy_config"],
            "economic_role_taxonomy_config",
        )
    )
    objectives = _normalize_objectives(
        ensure_mapping(
            values["role_objective_registry_config"],
            "role_objective_registry_config",
        ),
        taxonomy,
    )
    representation = _normalize_representation(
        ensure_mapping(
            values["population_representation_config"],
            "population_representation_config",
        ),
        taxonomy,
    )
    immutable = _path_list(
        policy["immutable_fields"],
        "immutable_fields",
    )
    state_speed = ensure_mapping(
        policy["state_speed_classes"],
        "state_speed_classes",
    )
    if set(state_speed) != {"slow", "medium", "fast"}:
        raise S4ContractError(
            "P3_S4_M02_STATE_CLASSES_INVALID",
            "state classes must be slow, medium and fast",
        )
    slow = _path_list(state_speed["slow"], "state_speed_classes.slow")
    medium = _string_list(
        state_speed["medium"],
        "state_speed_classes.medium",
    )
    fast = _string_list(state_speed["fast"], "state_speed_classes.fast")
    locations = ensure_mapping(
        policy["state_class_locations"],
        "state_class_locations",
    )
    expected_locations = {
        "immutable": "person_profile",
        "slow": "person_profile",
        "medium": "runtime_state",
        "fast": "runtime_state",
    }
    if locations != expected_locations:
        raise S4ContractError(
            "P3_S4_M02_STATE_CLASS_LOCATION_INVALID",
            f"expected {expected_locations}",
        )
    consistency_rules = _string_list(
        policy["consistency_rule_ids"],
        "consistency_rule_ids",
    )
    objective_policy = ensure_mapping(
        policy["objective_weight_policy"],
        "objective_weight_policy",
    )
    if objective_policy != objectives["weight_policy"]:
        raise S4ContractError(
            "P3_S4_M02_OBJECTIVE_POLICY_MISMATCH",
            "person policy and objective registry disagree",
        )
    schema_path = require_non_empty_string(
        policy["schema"],
        field="person_schema_policy_config.schema",
    )
    person_schema = resolve_schema_document(schema_path, config)
    schema_ref = _validate_person_schema(
        person_schema,
        {
            "immutable_fields": immutable,
            "state_speed_classes": {"slow": slow},
        },
        taxonomy,
        objectives,
    )
    output: dict[str, Any] = {
        "schema_id": "person_schema_policy.v2",
        "schema_version": "2.0.0",
        "contract_version": "p3.s4.person-policy.v2",
        "policy_id": require_non_empty_string(
            policy["policy_id"],
            field="policy_id",
        ),
        "policy_version": require_semver(
            policy["policy_version"],
            field="policy_version",
        ),
        "person_profile_schema": schema_ref,
        "tag_registry_ref": {
            "registry_id": tag_registry["registry_id"],
            "registry_version": tag_registry["registry_version"],
            "registry_hash": tag_registry["registry_hash"],
        },
        "role_taxonomy": taxonomy,
        "objective_registry": objectives,
        "representation_policy": representation,
        "immutable_field_paths": sorted(immutable),
        "structural_slow_field_paths": sorted(slow),
        "dynamic_state_classes": {
            "medium": sorted(medium),
            "fast": sorted(fast),
        },
        "state_class_locations": expected_locations,
        "consistency_rules": sorted(consistency_rules),
        "lineage_id": require_non_empty_string(
            policy["lineage_id"],
            field="policy.lineage_id",
        ),
        "status": "READY",
        "issues": [],
    }
    output["policy_hash"] = content_hash(output)
    SchemaRegistry(package_root()).validate(
        "schemas/person_schema_policy.schema.yaml",
        output,
        label="person_schema_policy",
    )
    LOGGER.info(
        "module_succeeded",
        extra={
            "module_id": "P3.S4.M02",
            "family_count": taxonomy["family_count"],
            "role_count": taxonomy["role_count"],
        },
    )
    return output
