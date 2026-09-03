from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any
import hashlib
import json
import stat
import zipfile

from ._module_executor import ContractValidationError
from ._p0_s7_common import digest

CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SECRET_NAMES = {".env", "id_rsa", "id_dsa", "id_ed25519", "credentials.json"}


def _finding(code: str, path: str, severity: str = "blocking", message: str = "") -> dict[str, Any]:
    fingerprint = digest({"code": code, "path": path})
    return {
        "finding_id": f"S7-{fingerprint[:12]}",
        "finding_fingerprint": fingerprint,
        "reason_code": code.upper(),
        "code": code,
        "path": path,
        "severity": severity,
        "message": message or code.replace("_", " "),
    }


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _inspect_entry(info, archive, state, limits):
    findings, entries, seen, seen_casefold = state
    max_file, max_ratio = limits
    name = info.filename
    pure = PurePosixPath(name)
    normalized = pure.as_posix()
    if pure.is_absolute() or ".." in pure.parts or "\\" in name:
        findings.append(_finding("unsafe_path", name))
    if normalized in seen:
        findings.append(_finding("duplicate_path", normalized))
    seen.add(normalized)
    folded = normalized.casefold()
    if folded in seen_casefold and seen_casefold[folded] != normalized:
        findings.append(_finding("case_collision", normalized))
    else:
        seen_casefold[folded] = normalized
    if _is_symlink(info):
        findings.append(_finding("symlink_entry", normalized))
    parts = set(pure.parts)
    if ".git" in parts:
        findings.append(_finding("git_metadata_in_zip", normalized))
    if any(part in CACHE_PARTS or part.endswith((".pyc", ".pyo")) for part in pure.parts):
        findings.append(_finding("cache_in_zip", normalized))
    if pure.name in SECRET_NAMES or pure.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        findings.append(_finding("secret_material_in_zip", normalized))
    if info.is_dir():
        return None
    if info.file_size > max_file:
        findings.append(_finding("file_too_large", normalized))
    ratio = info.file_size / max(info.compress_size, 1)
    if ratio > max_ratio and info.file_size > 1024:
        findings.append(_finding("compression_ratio_exceeded", normalized))
    if info.flag_bits & 0x1:
        findings.append(_finding("encrypted_entry", normalized))
    if info.file_size > max_file or (ratio > max_ratio and info.file_size > 1024) or info.flag_bits & 0x1:
        return None
    data = archive.read(info)
    entries.append({
        "path": normalized, "size": info.file_size,
        "compressed_size": info.compress_size,
        "compression_ratio": round(ratio, 6),
        "sha256": hashlib.sha256(data).hexdigest(),
        "entry_type": "file",
    })
    if normalized != "agent_manifest.json":
        return None
    try:
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("not a mapping")
        return parsed
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        findings.append(_finding("invalid_agent_manifest", normalized))
        return None


def inspect_package(package, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    limits = policy.get("package_limits", {}) if isinstance(policy.get("package_limits"), dict) else {}
    max_entries = int(limits.get("max_entries", 5000))
    max_total = int(limits.get("max_uncompressed_size", 250 * 1024 * 1024))
    max_file = int(limits.get("max_single_file_size", 50 * 1024 * 1024))
    max_ratio = float(limits.get("max_compression_ratio", 200.0))
    findings: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_casefold: dict[str, str] = {}
    agent_manifest: dict[str, Any] | None = None
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if not infos:
            raise ContractValidationError("agent package ZIP is empty")
        if len(infos) > max_entries:
            findings.append(_finding("too_many_entries", "<archive>"))
        declared_total = sum(info.file_size for info in infos if not info.is_dir())
        if declared_total > max_total:
            findings.append(_finding("archive_too_large", "<archive>"))
        # Complete central-directory preflight before reading a single member.
        preflight_seen: set[str] = set()
        preflight_folded: dict[str, str] = {}
        for info in infos:
            name = info.filename
            pure = PurePosixPath(name)
            normalized = pure.as_posix()
            ratio = info.file_size / max(info.compress_size, 1)
            if pure.is_absolute() or ".." in pure.parts or "\\" in name:
                findings.append(_finding("unsafe_path", name))
            if normalized in preflight_seen:
                findings.append(_finding("duplicate_path", normalized))
            preflight_seen.add(normalized)
            folded = normalized.casefold()
            if folded in preflight_folded and preflight_folded[folded] != normalized:
                findings.append(_finding("case_collision", normalized))
            preflight_folded[folded] = normalized
            if _is_symlink(info):
                findings.append(_finding("symlink_entry", normalized))
            if info.file_size > max_file:
                findings.append(_finding("file_too_large", normalized))
            if ratio > max_ratio and info.file_size > 1024:
                findings.append(_finding("compression_ratio_exceeded", normalized))
            if info.flag_bits & 0x1:
                findings.append(_finding("encrypted_entry", normalized))
        if findings:
            return [], findings, None
        for info in infos:
            parsed = _inspect_entry(
                info, archive, (findings, entries, seen, seen_casefold), (max_file, max_ratio)
            )
            if parsed is not None:
                agent_manifest = parsed
    return entries, findings, agent_manifest


def validate_required_files(entries: list[dict[str, Any]], required: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_path = {entry["path"]: entry for entry in entries}
    for expected in required:
        entry = by_path.get(expected)
        if entry is None:
            findings.append(_finding("required_file_missing", expected))
        elif entry["size"] == 0:
            findings.append(_finding("required_file_empty", expected))
    return findings


def validate_manifest(
    manifest: dict[str, Any] | None,
    policy: dict[str, Any],
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    require_manifest = bool(policy.get("require_agent_manifest", False))
    if manifest is None:
        return [_finding("agent_manifest_missing", "agent_manifest.json")] if require_manifest else []
    findings: list[dict[str, Any]] = []
    expected_policies = {value for value in (policy.get("artifact_id"), policy.get("policy_id")) if value}
    if expected_policies and manifest.get("execution_policy_id") not in expected_policies:
        findings.append(_finding("policy_binding_mismatch", "agent_manifest.json"))
    by_path = {entry["path"]: entry for entry in entries}
    records = manifest.get("files")
    if not isinstance(records, list):
        return [_finding("invalid_manifest_file_list", "agent_manifest.json")]
    manifest_paths = set()
    for record in records:
        if not isinstance(record, dict):
            findings.append(_finding("invalid_manifest_file_record", "agent_manifest.json"))
            continue
        path = record.get("path")
        if path in manifest_paths:
            findings.append(_finding("duplicate_manifest_path", str(path)))
        manifest_paths.add(path)
        expected_hash = record.get("sha256")
        actual = by_path.get(path)
        if actual is None:
            findings.append(_finding("manifest_file_missing", str(path)))
        elif expected_hash != actual["sha256"]:
            findings.append(_finding("manifest_hash_mismatch", str(path)))
    archive_paths = {entry["path"] for entry in entries if entry["path"] != "agent_manifest.json"}
    if archive_paths != manifest_paths:
        for path in sorted(archive_paths - manifest_paths):
            findings.append(_finding("unlisted_zip_entry", path))
        for path in sorted(manifest_paths - archive_paths):
            findings.append(_finding("manifest_file_missing", str(path)))
    return findings
