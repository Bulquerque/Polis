"""Public deterministic facade for the five P3.S33 modules."""

from __future__ import annotations

from typing import Any

from .contracts.artifacts import CanonicalToolOperationRegistry, ResearchToolExtensionSnapshot
from .contracts.boundary_artifacts import (
    EntityResolutionPolicy,
    Phase1CustodyQualificationReport,
    Phase1RawEvidenceReferenceIndex,
    Phase2ResearchViewManifest,
    Phase2ResearchViewReadinessReport,
    PitBoundaryQualificationReport,
    PitVisibilityPolicy,
    TemporalEntityResolutionIndex,
    VintagePolicyRegistry,
)
from .contracts.boundary_configs import (
    CalendarTimezonePolicyConfig,
    EntityUnderlyingMapConfig,
    PitDataViewPolicyConfig,
    VintagePolicyConfig,
)
from .services.boundary_bundle import build_boundary_bundle
from .services.custody import build_phase1_custody_index
from .services.entity_resolution import build_entity_resolution
from .services.temporal_boundary import build_temporal_boundary
from .services.views import build_phase2_views


def build_phase2_view_boundary(inputs: dict[str, Any]) -> dict[str, Any]:
    snapshot = ResearchToolExtensionSnapshot.model_validate(inputs["research_tool_extension_snapshot"], strict=False)
    manifest, readiness = build_phase2_views(
        inputs=inputs,
        operation_registry=CanonicalToolOperationRegistry.model_validate(
            inputs["canonical_tool_operation_registry"], strict=False
        ),
        extension_snapshot_hash=snapshot.snapshot_hash,
    )
    return {
        "phase2_research_view_manifest": manifest.model_dump(mode="json"),
        "phase2_research_view_readiness_report": readiness.model_dump(mode="json"),
    }


def build_phase1_custody_boundary(inputs: dict[str, Any]) -> dict[str, Any]:
    index, report = build_phase1_custody_index(
        inputs=inputs,
        view_manifest=Phase2ResearchViewManifest.model_validate(
            inputs["phase2_research_view_manifest"], strict=False
        ),
    )
    return {
        "phase1_raw_evidence_reference_index": index.model_dump(mode="json"),
        "phase1_custody_qualification_report": report.model_dump(mode="json"),
    }


def build_temporal_firewall(inputs: dict[str, Any]) -> dict[str, Any]:
    policy, vintages, report = build_temporal_boundary(
        phase3_run_snapshot=inputs["phase3_run_snapshot"],
        extension_snapshot=ResearchToolExtensionSnapshot.model_validate(
            inputs["research_tool_extension_snapshot"], strict=False
        ),
        view_manifest=Phase2ResearchViewManifest.model_validate(
            inputs["phase2_research_view_manifest"], strict=False
        ),
        raw_index=Phase1RawEvidenceReferenceIndex.model_validate(
            inputs["phase1_raw_evidence_reference_index"], strict=False
        ),
        evaluation_window_config=inputs["evaluation_window_config"],
        pit_config=PitDataViewPolicyConfig.model_validate(
            inputs["pit_data_view_policy_config"], strict=False
        ),
        timezone_config=CalendarTimezonePolicyConfig.model_validate(
            inputs["calendar_timezone_policy_config"], strict=False
        ),
        vintage_config=VintagePolicyConfig.model_validate(
            inputs["vintage_policy_config"], strict=False
        ),
    )
    return {
        "pit_visibility_policy": policy.model_dump(mode="json"),
        "vintage_policy_registry": vintages.model_dump(mode="json"),
        "pit_boundary_qualification_report": report.model_dump(mode="json"),
    }


def build_entity_resolution_boundary(inputs: dict[str, Any]) -> dict[str, Any]:
    index, policy, report = build_entity_resolution(
        inputs=inputs,
        config=EntityUnderlyingMapConfig.model_validate(
            inputs["entity_underlying_map_config"], strict=False
        ),
        view_manifest=Phase2ResearchViewManifest.model_validate(
            inputs["phase2_research_view_manifest"], strict=False
        ),
        pit_policy=PitVisibilityPolicy.model_validate(inputs["pit_visibility_policy"], strict=False),
    )
    return {
        "temporal_entity_resolution_index": index.model_dump(mode="json"),
        "entity_resolution_policy": policy.model_dump(mode="json"),
        "entity_resolution_qualification_report": report.model_dump(mode="json"),
    }


def build_research_data_boundary_bundle(inputs: dict[str, Any]) -> dict[str, Any]:
    bundle, report = build_boundary_bundle(
        extension_snapshot=ResearchToolExtensionSnapshot.model_validate(
            inputs["research_tool_extension_snapshot"], strict=False
        ),
        view_manifest=Phase2ResearchViewManifest.model_validate(
            inputs["phase2_research_view_manifest"], strict=False
        ),
        view_readiness=Phase2ResearchViewReadinessReport.model_validate(
            inputs["phase2_research_view_readiness_report"], strict=False
        ),
        raw_index=Phase1RawEvidenceReferenceIndex.model_validate(
            inputs["phase1_raw_evidence_reference_index"], strict=False
        ),
        custody_report=Phase1CustodyQualificationReport.model_validate(
            inputs["phase1_custody_qualification_report"], strict=False
        ),
        pit_policy=PitVisibilityPolicy.model_validate(inputs["pit_visibility_policy"], strict=False),
        vintage_registry=VintagePolicyRegistry.model_validate(
            inputs["vintage_policy_registry"], strict=False
        ),
        pit_report=PitBoundaryQualificationReport.model_validate(
            inputs["pit_boundary_qualification_report"], strict=False
        ),
        entity_index=TemporalEntityResolutionIndex.model_validate(
            inputs["temporal_entity_resolution_index"], strict=False
        ),
        entity_policy=EntityResolutionPolicy.model_validate(
            inputs["entity_resolution_policy"], strict=False
        ),
    )
    return {
        "research_data_boundary_bundle": bundle.model_dump(mode="json"),
        "research_boundary_preflight_report": report.model_dump(mode="json"),
    }
