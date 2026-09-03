"""Release-level consistency checks used by ``p3 validate`` and CI."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a mapping")
    return value


def validate_schema_registry_hashes(root: Path) -> list[str]:
    errors: list[str] = []
    copies = (
        (root / "schemas/SCHEMA_REGISTRY.yaml", root / "schemas"),
        (root / "contracts/SCHEMA_REGISTRY.yaml", root / "schemas"),
        (
            root / "src/quant_pipeline/phase_03_agents_rag_memory/assets/schemas/SCHEMA_REGISTRY.yaml",
            root / "src/quant_pipeline/phase_03_agents_rag_memory/assets/schemas",
        ),
    )
    canonical: bytes | None = None
    for registry_path, schema_root in copies:
        if not registry_path.is_file():
            errors.append(f"missing schema registry: {registry_path.relative_to(root)}")
            continue
        document = _load_yaml(registry_path)
        rows = document.get("schemas")
        if not isinstance(rows, list) or document.get("schema_count") != len(rows):
            errors.append(f"invalid schema_count in {registry_path.relative_to(root)}")
            continue
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("schema"), str):
                errors.append(f"invalid schema row in {registry_path.relative_to(root)}")
                continue
            target = schema_root / row["schema"]
            if not target.is_file():
                errors.append(f"missing registered schema: {target.relative_to(root)}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != row.get("sha256"):
                errors.append(
                    f"schema hash mismatch {registry_path.relative_to(root)}::{row['schema']} expected={row.get('sha256')} actual={actual}"
                )
        raw = registry_path.read_bytes()
        if canonical is None:
            canonical = raw
        elif raw != canonical:
            errors.append(f"schema registry copies differ: {registry_path.relative_to(root)}")
    return errors



def validate_global_schema_versions(root: Path) -> list[str]:
    errors: list[str] = []
    expected = "v14.1-rc4.1"
    artifact_schema_versions = {"mcp_gateway_policy.schema.yaml": "2.0.0"}
    for path in sorted(root.rglob("*.schema.yaml")):
        if any(part in {"__pycache__", ".pytest_cache", "build", "dist"} for part in path.parts):
            continue
        try:
            document = _load_yaml(path)
        except Exception as exc:
            errors.append(f"invalid schema document {path.relative_to(root)}: {exc}")
            continue
        expected_for_schema = artifact_schema_versions.get(path.name, expected)
        if document.get("schema_version") != expected_for_schema:
            errors.append(
                f"schema release version mismatch {path.relative_to(root)}: "
                f"{document.get('schema_version')} != {expected_for_schema}"
            )
    if not (root / "SOURCE_OF_TRUTH.md").is_file():
        errors.append("missing SOURCE_OF_TRUTH.md")
    return errors

def validate_documentation_links(root: Path) -> list[str]:
    errors: list[str] = []
    for module_path in sorted((root / "modules").glob("*.yaml")):
        document = _load_yaml(module_path)
        owner = document.get("owner_prompt")
        if not isinstance(owner, str) or not (root / owner).is_file():
            errors.append(f"invalid owner_prompt in {module_path.relative_to(root)}: {owner}")
    if not (root / "docs/MODULE_INDEX.md").is_file():
        errors.append("missing docs/MODULE_INDEX.md")
    return errors


def validate_global_authority_patch(root: Path) -> list[str]:
    errors: list[str] = []
    names = (
        "clean_context_source_panel",
        "clean_document_panel",
        "clean_event_reference_panel",
        "source_quality_panel",
        "context_handoff_manifest",
        "phase3_handoff_manifest",
        "hypothesis_registry",
    )
    patch_root = root / "integration/new_version_sanitized/global_authority_patch/schemas"
    for name in names:
        patch = patch_root / f"{name}.schema.yaml"
        local = root / "schemas" / f"{name}.schema.yaml"
        if not patch.is_file():
            errors.append(f"missing global authority patch schema: {name}")
        elif not local.is_file() or patch.read_bytes() != local.read_bytes():
            errors.append(f"global authority patch differs from local authority: {name}")
    return errors



def validate_final_integration_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    copies = (
        (
            root / "schemas/final_integration/FINAL_INTEGRATION_SCHEMA_REGISTRY.yaml",
            root / "schemas/final_integration",
        ),
        (
            root / "assets/schemas/final_integration/FINAL_INTEGRATION_SCHEMA_REGISTRY.yaml",
            root / "assets/schemas/final_integration",
        ),
        (
            root
            / "src/quant_pipeline/phase_03_agents_rag_memory/assets/schemas/final_integration/FINAL_INTEGRATION_SCHEMA_REGISTRY.yaml",
            root
            / "src/quant_pipeline/phase_03_agents_rag_memory/assets/schemas/final_integration",
        ),
    )
    canonical: bytes | None = None
    for registry_path, schema_root in copies:
        if not registry_path.is_file():
            errors.append(
                f"missing final-integration schema registry: {registry_path.relative_to(root)}"
            )
            continue
        document = _load_yaml(registry_path)
        rows = document.get("schemas")
        if not isinstance(rows, list) or document.get("schema_count") != len(rows):
            errors.append(
                f"invalid final-integration schema_count: {registry_path.relative_to(root)}"
            )
            continue
        if len(rows) != 16:
            errors.append("final-integration schema registry must contain 16 schemas")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("schema"), str):
                errors.append(
                    f"invalid final-integration schema row: {registry_path.relative_to(root)}"
                )
                continue
            target = schema_root / row["schema"]
            if not target.is_file():
                errors.append(f"missing final-integration schema: {target.relative_to(root)}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != row.get("sha256"):
                errors.append(f"final-integration schema hash mismatch: {row['schema']}")
        raw = registry_path.read_bytes()
        if canonical is None:
            canonical = raw
        elif raw != canonical:
            errors.append(
                f"final-integration schema registries differ: {registry_path.relative_to(root)}"
            )

    binding_copies = (
        root / "contracts/FINAL_INTEGRATION_ARTIFACT_SCHEMA_BINDINGS.yaml",
        root / "assets/contracts/FINAL_INTEGRATION_ARTIFACT_SCHEMA_BINDINGS.yaml",
        root
        / "src/quant_pipeline/phase_03_agents_rag_memory/assets/contracts/FINAL_INTEGRATION_ARTIFACT_SCHEMA_BINDINGS.yaml",
    )
    binding_raw: bytes | None = None
    for path in binding_copies:
        if not path.is_file():
            errors.append(
                f"missing final-integration binding registry: {path.relative_to(root)}"
            )
            continue
        document = _load_yaml(path)
        rows = document.get("bindings")
        if not isinstance(rows, list) or len(rows) != 16:
            errors.append(
                f"final-integration binding registry must have 16 rows: {path.relative_to(root)}"
            )
        for row in rows or []:
            schema = row.get("schema") if isinstance(row, dict) else None
            if not isinstance(schema, str) or not (root / schema).is_file():
                errors.append(
                    f"invalid final-integration binding in {path.relative_to(root)}: {row}"
                )
        raw = path.read_bytes()
        if binding_raw is None:
            binding_raw = raw
        elif raw != binding_raw:
            errors.append(
                f"final-integration binding copies differ: {path.relative_to(root)}"
            )

    required_files = (
        "INTEGRATION_GUIDE.md",
        "integration/final/MODULE_CHANGE_MANIFEST.yaml",
        "integration/final/ACCEPTANCE_GATES.yaml",
        "integration/final/RISK_REGISTER.csv",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"missing final integration documentation: {relative}")

    manifest_path = root / "integration/final/MODULE_CHANGE_MANIFEST.yaml"
    if manifest_path.is_file():
        manifest = _load_yaml(manifest_path)
        modules = manifest.get("modules")
        if (
            not isinstance(modules, list)
            or manifest.get("module_count") != 44
            or len(modules) != 44
        ):
            errors.append("final integration module manifest must contain exactly 44 modules")
        else:
            for row in modules:
                module_id = row.get("module_id") if isinstance(row, dict) else None
                if not isinstance(module_id, str):
                    errors.append(f"invalid final integration module row: {row}")
                    continue
                copies_found: list[dict[str, Any]] = []
                for base in (root / "modules", root / "contracts/modules"):
                    candidates = list(base.glob(f"{module_id.replace('.', '_')}_*.yaml"))
                    if len(candidates) != 1:
                        errors.append(
                            f"module contract resolution failed: {module_id} in {base.relative_to(root)}"
                        )
                        continue
                    document = _load_yaml(candidates[0])
                    section = document.get("final_integration")
                    if (
                        not isinstance(section, dict)
                        or section.get("qualification_policy")
                        != "REAL_PIPELINE_ONLY_FAIL_CLOSED"
                    ):
                        errors.append(
                            f"missing final integration section: {candidates[0].relative_to(root)}"
                        )
                    copies_found.append(section)
                if len(copies_found) == 2 and copies_found[0] != copies_found[1]:
                    errors.append(f"module contract copies differ: {module_id}")

    deprecated_identifier = re.compile(r"(?:W[0-9]\.G[0-9]|P3R(?:11|12|13|14|15|16|17)|P3\.W[A-Z_]+)")
    official_files = (
        root / "README.md",
        root / "START_HERE.md",
        root / "INTEGRATION_GUIDE.md",
        root / "src/quant_pipeline/phase_03_agents_rag_memory/final_integration",
        root / "integration/final",
    )
    for base in official_files:
        paths = [base] if base.is_file() else list(base.rglob("*")) if base.is_dir() else []
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".json", ".csv"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = deprecated_identifier.search(text)
            if match:
                errors.append(
                    f"deprecated release identifier in official surface: {path.relative_to(root)}::{match.group(0)}"
                )
    return errors


def validate_release_identity(root: Path) -> list[str]:
    """Verify the stable package content digest recorded in RELEASE.json."""
    release_path = root / "RELEASE.json"
    if not release_path.is_file():
        return ["missing RELEASE.json"]
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid RELEASE.json: {exc}"]
    excluded_names = {
        "RELEASE.json", "ASSET_MIRROR_MANIFEST.json", "PACKAGE_MANIFEST.json",
        "FILE_MANIFEST.json", "MANIFESTO.csv",
    }
    excluded_parts = {
        ".git", ".venv", ".venv-p3", "venv", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".hypothesis", "htmlcov", "build", "dist",
    }
    excluded_suffixes = {".pyc", ".pyo", ".zip", ".whl"}
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if path.name in excluded_names or path.suffix in excluded_suffixes:
            continue
        if any(part in excluded_parts or part.endswith(".egg-info") for part in relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    actual = digest.hexdigest()
    errors: list[str] = []
    if release.get("content_sha256") != actual:
        errors.append(
            f"release content hash mismatch expected={release.get('content_sha256')} actual={actual}"
        )
    if release.get("canonical_module_count") != 81:
        errors.append("RELEASE.json canonical_module_count must be 81")
    if release.get("production_promotion_allowed") is not False:
        errors.append("Phase 3 release cannot self-promote")
    if release.get("promotion_authority") != "P0_ONLY":
        errors.append("promotion authority must be P0_ONLY")
    return errors


__all__ = [
    "validate_documentation_links",
    "validate_global_authority_patch",
    "validate_global_schema_versions",
    "validate_schema_registry_hashes",
    "validate_final_integration_contracts",
    "validate_release_identity",
]
