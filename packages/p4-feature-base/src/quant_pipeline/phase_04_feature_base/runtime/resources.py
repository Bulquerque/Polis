from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Any

from .yaml_loader import load_yaml

_RESOURCE_PACKAGE = "quant_pipeline.phase_04_feature_base._resources"


def resource_root() -> Traversable:
    """Return the installed package resource root without assuming a filesystem path."""
    return files(_RESOURCE_PACKAGE)


def upstream_schema_root(source: str) -> Traversable:
    """Return the packaged compatibility-schema directory for an upstream phase."""
    if source not in {"p2", "p3"}:
        raise ValueError(f"unsupported upstream schema source: {source!r}")
    return resource_root().joinpath("upstream_schemas", source)


def output_schemas() -> dict[str, dict[str, Any]]:
    """Load all P4.S1 output schemas bundled inside the installed package."""
    names = (
        "validated_phase2_bundle",
        "phase2_capability_matrix",
        "validated_phase3_bundle",
        "phase3_capability_matrix",
        "validated_p4_boundary_bundle",
        "boundary_consistency_report",
        "observer_change_proposal_registry",
    )
    schema_root = resource_root().joinpath("schemas")
    return {
        name: load_yaml(schema_root.joinpath(f"{name}.schema.yaml"))
        for name in names
    }


def s2_output_schemas() -> dict[str, dict[str, Any]]:
    """Load all P4.S2 output schemas bundled inside the installed package."""
    names = (
        "temporally_resolved_observation_bundle",
        "temporal_resolution_report",
        "entity_aligned_observation_bundle",
        "entity_alignment_report",
        "quality_enriched_observation_bundle",
        "availability_missingness_panel",
        "revision_selection_report",
        "canonical_observation_panel",
        "canonical_store_manifest",
    )
    schema_root = resource_root().joinpath("schemas")
    return {
        name: load_yaml(schema_root.joinpath(f"{name}.schema.yaml"))
        for name in names
    }


def s1_output_schemas() -> dict[str, dict[str, Any]]:
    """Alias retained for explicit S1→S2 validation."""
    return output_schemas()


def s3_output_schemas() -> dict[str, dict[str, Any]]:
    names = (
        "feature_observer_registry", "feature_parameter_policy_registry",
        "foundational_hypothesis_core_registry", "validated_observer_spec_registry",
        "observer_spec_validation_report", "approved_hypothesis_passport_registry",
        "approved_observer_execution_registry", "approved_interaction_registry",
        "hypothesis_budget_report", "rejected_hypothesis_registry",
        "observer_change_review_registry", "observer_change_decision_registry",
        "causal_operator_execution_plan", "relational_operator_execution_plan",
        "causal_operator_result_panel", "operator_fit_state_registry",
        "relational_operator_result_panel", "relational_fit_state_registry",
    )
    root = resource_root().joinpath("schemas")
    return {name: load_yaml(root.joinpath(f"{name}.schema.yaml")) for name in names}

def s3_registries() -> dict[str, dict[str, Any]]:
    names = ("FEATURE_FAMILY_REGISTRY", "FOUNDATIONAL_HYPOTHESIS_CORE",
             "OBSERVER_SPEC_REGISTRY", "INTERACTION_REGISTRY",
             "FEATURE_PARAMETER_POLICY")
    root = resource_root().joinpath("registries")
    return {name: load_yaml(root.joinpath(f"{name}.yaml")) for name in names}
