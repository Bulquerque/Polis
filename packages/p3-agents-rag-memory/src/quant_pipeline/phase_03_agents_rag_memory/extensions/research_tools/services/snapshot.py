"""P3.S32.M04 implementation."""

from __future__ import annotations

from collections import Counter

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    CompatibilityAliasRegistry,
    ContractPackFile,
    ProviderTransportOverlay,
    ResearchModeRegistry,
    ResearchToolContractPackManifest,
    ResearchToolExtensionSnapshot,
    SnapshotComponent,
)
from ..contracts.configs import (
    ExtensionConfigManifest,
    PromptDescriptorTemplateManifest,
    SchemaBundleManifest,
)
from ..core.errors import fail
from ..core.hashing import content_hash
from .artifact_construction import finalize, lineage


def _major(version: str) -> int:
    return int(version.split(".", 1)[0])


def _artifact_hash(value: object) -> str:
    existing = getattr(value, "content_hash", None)
    return str(existing) if existing is not None else content_hash(value)



def _canonical_manifests(
    schema_manifest: SchemaBundleManifest,
    prompt_manifest: PromptDescriptorTemplateManifest,
    config_manifest: ExtensionConfigManifest,
) -> tuple[SchemaBundleManifest, PromptDescriptorTemplateManifest, ExtensionConfigManifest]:
    return (
        schema_manifest.model_copy(
            update={"entries": tuple(sorted(schema_manifest.entries, key=lambda item: item.relative_path))}
        ),
        prompt_manifest.model_copy(
            update={"files": tuple(sorted(prompt_manifest.files, key=lambda item: item.relative_path))}
        ),
        config_manifest.model_copy(
            update={"files": tuple(sorted(config_manifest.files, key=lambda item: item.relative_path))}
        ),
    )


def build_snapshot(
    *,
    catalog: CanonicalResearchToolCatalog,
    operation_registry: CanonicalToolOperationRegistry,
    mode_registry: ResearchModeRegistry,
    operation_mode_matrix: object,
    provider_overlay: ProviderTransportOverlay,
    alias_registry: CompatibilityAliasRegistry,
    schema_manifest: SchemaBundleManifest,
    prompt_manifest: PromptDescriptorTemplateManifest,
    config_manifest: ExtensionConfigManifest,
) -> tuple[ResearchToolExtensionSnapshot, ResearchToolContractPackManifest]:
    schema_manifest, prompt_manifest, config_manifest = _canonical_manifests(
        schema_manifest, prompt_manifest, config_manifest
    )
    version = catalog.contract_version
    if _major(version) != 1:
        raise fail(
            "P3RT-CONTRACT-0015",
            "parallel production only accepts contract major version 1",
            {"contract_version": version},
        )
    component_sources = {
        "catalog": catalog,
        "operations": operation_registry,
        "modes": mode_registry,
        "operation_mode_matrix": operation_mode_matrix,
        "providers": provider_overlay,
        "aliases": alias_registry,
        "schemas": schema_manifest,
        "prompt_descriptors": prompt_manifest,
        "configuration": config_manifest,
    }
    components = tuple(
        SnapshotComponent(
            component_id=component_id,
            version=version,
            content_hash=_artifact_hash(value),
            kind="ARTIFACT" if hasattr(value, "artifact_id") else "MANIFEST",
        )
        for component_id, value in sorted(component_sources.items())
    )
    expected_handler_ids = tuple(sorted({item.handler_id for item in operation_registry.operations}))
    provider_fingerprints = tuple(sorted({item.fingerprint for item in provider_overlay.providers}))
    snapshot_identity = {
        "contract_version": version,
        "components": components,
        "expected_handler_ids": expected_handler_ids,
        "provider_fingerprints": provider_fingerprints,
    }
    snapshot_hash = content_hash(snapshot_identity)
    source_inputs = tuple(component_sources.values())
    snapshot = finalize(
        ResearchToolExtensionSnapshot,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M04", version, source_inputs),
            "contract_version": version,
            "snapshot_hash": snapshot_hash,
            "components": components,
            "expected_handler_ids": expected_handler_ids,
            "provider_fingerprints": provider_fingerprints,
        },
    )

    files = [
        ContractPackFile(
            relative_path=item.relative_path,
            kind=item.kind,
            sha256=item.sha256,
            size_bytes=item.size_bytes,
        )
        for item in schema_manifest.entries
    ]
    files.extend(
        ContractPackFile(
            relative_path=item.relative_path,
            kind=item.kind,
            sha256=item.sha256,
            size_bytes=item.size_bytes,
        )
        for manifest in (prompt_manifest, config_manifest)
        for item in manifest.files
    )
    duplicate_paths = sorted(
        path for path, count in Counter(item.relative_path for item in files).items() if count > 1
    )
    if duplicate_paths:
        raise fail(
            "P3RT-CONTRACT-0016",
            "contract pack contains duplicate paths",
            {"paths": duplicate_paths},
        )
    ordered_files = tuple(sorted(files, key=lambda item: item.relative_path))
    manifest = finalize(
        ResearchToolContractPackManifest,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M04", version, source_inputs),
            "contract_version": version,
            "files": ordered_files,
            "file_count": len(ordered_files),
            "schema_count": len(schema_manifest.entries),
            "expected_handler_count": len(expected_handler_ids),
        },
    )
    return snapshot, manifest
