from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s3_artifacts import artifact_records, mapping_or_path
from ._p0_s3_shared import (
    SHA256_RE,
    created_at,
    find_forbidden_fields,
    normalized_version,
    require_runtime_version,
    safe_repo_path,
    sha256_file,
    stable_digest,
    strictly_newer_version,
    validate_output,
    workspace_root,
)


def _timeline_document(value: Any, label: str) -> tuple[dict[str, Any], Path, str]:
    if isinstance(value, dict) and "path" not in value:
        return value, workspace_root(), f"inline:{label}"
    document, source = mapping_or_path(value, label)
    path = workspace_root() / source
    return document, path.parent if path.exists() else workspace_root(), source


def _timeline_entries(value: Any, label: str, *, allow_genesis: bool = False):
    document, base, source = _timeline_document(value, label)
    leaked = find_forbidden_fields(document, label)
    if leaked:
        raise ContractValidationError(f"forbidden {label} fields detected: {leaked}")
    genesis = bool(document.get("genesis"))
    entries = next((document[key] for key in ("entries", "artifacts", "history") if key in document), None)
    if genesis and allow_genesis and entries in (None, []):
        return [], base, source, document, True
    if not isinstance(entries, list) or not entries or not all(isinstance(entry, dict) for entry in entries):
        raise ContractValidationError(f"{label} must contain non-empty artifact entries")
    if label == "release_manifest_previous" and not genesis and not any(
        document.get(key) for key in ("release_id", "release_version", "pipeline_version")
    ):
        raise ContractValidationError("release_manifest_previous lacks release identity")
    return entries, base, source, document, genesis


def _schema_version(record: dict[str, Any], path: Path) -> str:
    declared = record.get("schema_version") or record.get("version")
    if path.is_file() and path.name.endswith(".schema.yaml"):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ContractValidationError(f"current schema YAML is malformed: {path}: {exc}") from exc
        if isinstance(document, dict) and document.get("schema_version"):
            file_version = str(document["schema_version"])
            if declared not in (None, "") and normalized_version(declared) != normalized_version(file_version):
                raise ContractValidationError(f"declared schema version differs from file content: {path}")
            return file_version
    return str(declared or "")


def _version_bumped(previous: str, current: str) -> bool:
    return bool(previous and current and strictly_newer_version(previous, current))


def _current_entries(value: Any):
    records, sources = artifact_records(value)
    entries = []
    for record in records:
        entries.append(
            {
                "identity": record.artifact_id,
                "path": record.path,
                "resolved_path": record.resolved_path,
                "declared_hash": record.declared_hash,
                "schema_version": _schema_version(record.raw, record.resolved_path),
                "raw": record.mutability_class == "IMMUTABLE" and (
                    str(record.raw.get("artifact_type", "")).lower() == "raw" or "raw" in Path(record.path).parts
                ),
                "mutability_class": record.mutability_class,
                "stable_identity": record.stable_identity,
                "source": record.source,
                "raw_record": record.raw,
            }
        )
    if not entries:
        raise ContractValidationError("artifact_manifest_all_phases contains no artifacts")
    return entries, len(sources)


def _normalize_past(record: dict[str, Any], base: Path, source: str) -> dict[str, Any]:
    leaked = find_forbidden_fields(record, source)
    if leaked:
        raise ContractValidationError(f"forbidden artifact fields detected: {leaked}")
    raw_path = record.get("path") or record.get("artifact_path") or record.get("file_path")
    if not isinstance(raw_path, str):
        raise ContractValidationError(f"artifact path is missing in {source}")
    resolved, relative = safe_repo_path(raw_path, base, "historical artifact path")
    digest = record.get("sha256") or record.get("hash") or record.get("digest") or ""
    digest = str(digest).removeprefix("sha256:").lower()
    if SHA256_RE.fullmatch(digest) is None:
        raise ContractValidationError(f"historical hash is missing or malformed: {relative}")
    identity = record.get("artifact_id") or record.get("identity") or relative
    if not isinstance(identity, str) or not identity.strip():
        raise ContractValidationError(f"artifact identity is malformed: {relative}")
    mutability = str(record.get("mutability_class") or "").upper()
    if not mutability:
        artifact_type = str(record.get("artifact_type") or record.get("type") or "").lower()
        mutability = "IMMUTABLE" if artifact_type == "raw" or "raw" in Path(relative).parts else (
            "VERSIONED" if relative.endswith(".schema.yaml") else "REPLACEABLE"
        )
    return {
        "identity": identity.strip(),
        "path": relative,
        "resolved_path": resolved,
        "declared_hash": digest,
        "schema_version": str(record.get("schema_version") or record.get("version") or ""),
        "raw": mutability == "IMMUTABLE" and (str(record.get("artifact_type", "")).lower() == "raw" or "raw" in Path(relative).parts),
        "mutability_class": mutability,
        "stable_identity": bool(record.get("artifact_id") or record.get("identity")),
        "source": source,
        "raw_record": record,
    }


def _past_entries(value: Any, label: str, *, allow_genesis: bool = False):
    records, base, source, document, genesis = _timeline_entries(value, label, allow_genesis=allow_genesis)
    entries = [_normalize_past(record, base, source) for record in records]
    identities = [entry["identity"] for entry in entries]
    paths = [entry["path"] for entry in entries]
    if len(identities) != len(set(identities)) or len(paths) != len(set(paths)):
        raise ContractValidationError(f"{label} contains duplicate identity or path")
    return entries, document, genesis


def _history_chain_status(document: dict[str, Any]) -> tuple[bool, str]:
    entries = document.get("entries") or document.get("history") or document.get("artifacts") or []
    if not entries:
        return True, "GENESIS"
    chained = [entry for entry in entries if "record_hash" in entry or "previous_record_hash" in entry]
    if not chained:
        return True, "LEGACY_UNCHAINED"
    if len(chained) != len(entries):
        return False, "PARTIAL_CHAIN"
    previous = str(document.get("chain_root") or "")
    for entry in entries:
        declared_previous = str(entry.get("previous_record_hash") or "")
        if declared_previous != previous:
            return False, "CHAIN_LINK_MISMATCH"
        payload = {key: value for key, value in entry.items() if key not in {"record_hash", "previous_record_hash"}}
        computed = stable_digest({"previous_record_hash": previous, "payload": payload})
        if entry.get("record_hash") != computed:
            return False, "CHAIN_HASH_MISMATCH"
        previous = computed
    return True, "CHAINED_VALID"


def _finding(code, identity, current_path, previous_path, current_hash, previous_hash, message, *, severity="CRITICAL"):
    return {
        "code": code,
        "severity": severity,
        "artifact_identity": identity,
        "current_path": current_path,
        "previous_path": previous_path,
        "current_hash": current_hash,
        "previous_hash": previous_hash,
        "message": message,
        "release_blocking": severity == "CRITICAL",
    }


def _index_current(current, findings):
    by_identity: dict[str, dict[str, Any]] = {}
    by_path: dict[str, dict[str, Any]] = {}
    for entry in current:
        if not entry["stable_identity"]:
            findings.append(_finding("LEGACY_PATH_IDENTITY", entry["identity"], entry["path"], "", entry["declared_hash"], "", "Artifact uses path fallback instead of stable artifact_id", severity="WARNING"))
        if entry["identity"] in by_identity:
            findings.append(_finding("IDENTITY_REUSE", entry["identity"], entry["path"], by_identity[entry["identity"]]["path"], entry["declared_hash"], by_identity[entry["identity"]]["declared_hash"], "Current manifest reuses an artifact identity"))
        if entry["path"] in by_path and by_path[entry["path"]]["identity"] != entry["identity"]:
            findings.append(_finding("IDENTITY_REUSE", entry["identity"], entry["path"], by_path[entry["path"]]["path"], entry["declared_hash"], by_path[entry["path"]]["declared_hash"], "Current manifest assigns multiple identities to one path"))
        by_identity.setdefault(entry["identity"], entry)
        by_path.setdefault(entry["path"], entry)
        _check_current_content(entry, findings)
    return by_identity, by_path


def _check_current_content(entry, findings):
    if SHA256_RE.fullmatch(entry["declared_hash"]) is None:
        findings.append(_finding("CURRENT_HASH_MISSING", entry["identity"], entry["path"], "", entry["declared_hash"], "", "Current manifest hash is missing or malformed"))
    elif not entry["resolved_path"].is_file():
        findings.append(_finding("CURRENT_FILE_MISSING", entry["identity"], entry["path"], "", entry["declared_hash"], "", "Current artifact file does not exist"))
    else:
        actual = sha256_file(entry["resolved_path"])
        if actual != entry["declared_hash"]:
            findings.append(_finding("CURRENT_HASH_MISMATCH", entry["identity"], entry["path"], "", actual, entry["declared_hash"], "Current artifact content does not match its declared hash"))


def _compare_baselines(current_by_identity, current_by_path, history, previous_release, findings):
    history_by_id = {entry["identity"]: entry for entry in history}
    release_by_id = {entry["identity"]: entry for entry in previous_release}
    for identity in sorted(set(history_by_id) & set(release_by_id)):
        historic, released = history_by_id[identity], release_by_id[identity]
        fields = ("path", "declared_hash", "schema_version", "mutability_class")
        if any(historic[field] != released[field] for field in fields):
            findings.append(_finding("HISTORY_RELEASE_CONFLICT", identity, "", released["path"], historic["declared_hash"], released["declared_hash"], "Hash history conflicts with the previous release manifest"))
    baseline = {**history_by_id, **release_by_id}
    baseline_by_path = {entry["path"]: entry for entry in baseline.values()}
    checked = 0
    for identity, entry in sorted(current_by_identity.items()):
        previous = baseline.get(identity)
        same_path = baseline_by_path.get(entry["path"])
        if previous is None and same_path is not None:
            findings.append(_finding("IDENTITY_REUSE", identity, entry["path"], same_path["path"], entry["declared_hash"], same_path["declared_hash"], "Existing artifact path was assigned a different identity"))
            continue
        if previous is None:
            continue
        checked += 1
        _compare_entry(entry, previous, findings)
    _detect_removed_artifacts(current_by_identity, baseline, findings)
    return checked


def _compare_entry(entry, previous, findings):
    if previous["path"] != entry["path"]:
        findings.append(_finding("IDENTITY_REUSE", entry["identity"], entry["path"], previous["path"], entry["declared_hash"], previous["declared_hash"], "Artifact identity moved to a different path"))
    changed = entry["declared_hash"] != previous["declared_hash"]
    policy = entry["mutability_class"] or previous["mutability_class"]
    if changed and (entry["raw"] or previous["raw"]):
        findings.append(_finding("RAW_OVERWRITE", entry["identity"], entry["path"], previous["path"], entry["declared_hash"], previous["declared_hash"], "Immutable raw artifact content changed in place"))
    elif changed and policy in {"IMMUTABLE", "APPEND_ONLY"}:
        findings.append(_finding("MUTABILITY_POLICY_VIOLATION", entry["identity"], entry["path"], previous["path"], entry["declared_hash"], previous["declared_hash"], f"{policy} artifact content changed in place"))
    if changed and policy == "VERSIONED" and not _version_bumped(previous["schema_version"], entry["schema_version"]):
        findings.append(_finding("SCHEMA_VERSION_NOT_BUMPED", entry["identity"], entry["path"], previous["path"], entry["declared_hash"], previous["declared_hash"], "Versioned artifact changed without a strictly greater schema/version value"))


def _detect_removed_artifacts(current_by_identity, baseline, findings):
    for identity, previous in sorted(baseline.items()):
        if identity in current_by_identity:
            continue
        policy = previous["mutability_class"]
        if policy == "IMMUTABLE":
            findings.append(_finding("IMMUTABLE_ARTIFACT_REMOVED", identity, "", previous["path"], "", previous["declared_hash"], "Immutable artifact disappeared from the current snapshot"))
        elif policy == "APPEND_ONLY":
            findings.append(_finding("APPEND_ONLY_HISTORY_TRUNCATED", identity, "", previous["path"], "", previous["declared_hash"], "Append-only artifact disappeared from the current snapshot"))


def _load_state(inputs):
    current, _ = _current_entries(inputs["artifact_manifest_all_phases"])
    release, release_doc, genesis = _past_entries(
        inputs["release_manifest_previous"], "release_manifest_previous", allow_genesis=True
    )
    history, history_doc, history_genesis = _past_entries(
        inputs["hash_history"], "hash_history", allow_genesis=genesis
    )
    if genesis != history_genesis and not history:
        raise ContractValidationError("genesis baseline requires hash_history genesis declaration")
    chain_valid, chain_mode = _history_chain_status(history_doc)
    return current, history, release, genesis, chain_valid, chain_mode


def _collect_findings(current, history, release, genesis, chain_valid, chain_mode):
    findings = []
    if not chain_valid:
        findings.append(_finding(
            "HISTORY_CHAIN_BROKEN", "hash_history", "", "", "", "",
            f"Hash history chain is invalid: {chain_mode}"
        ))
    current_by_identity, current_by_path = _index_current(current, findings)
    checked = 0 if genesis else _compare_baselines(
        current_by_identity, current_by_path, history, release, findings
    )
    unique = {}
    for finding in findings:
        key = (finding["code"], finding["artifact_identity"], finding["current_path"], finding["previous_path"])
        unique[key] = finding
    findings = [{"finding_id": f"IM-{i:05d}", **unique[key]} for i, key in enumerate(sorted(unique), 1)]
    return findings, checked


def _report(current, history, release, genesis, chain_valid, chain_mode, findings, checked, config):
    codes = [item["code"] for item in findings]
    count = lambda code: codes.count(code)
    blocking = any(item["release_blocking"] for item in findings)
    warning = any(item["severity"] == "WARNING" for item in findings)
    normalized = {
        "current": [{k: e[k] for k in ("identity", "path", "declared_hash", "schema_version", "mutability_class")} for e in current],
        "history": [{k: e[k] for k in ("identity", "path", "declared_hash", "schema_version", "mutability_class")} for e in history],
        "previous_release": [{k: e[k] for k in ("identity", "path", "declared_hash", "schema_version", "mutability_class")} for e in release],
        "genesis": genesis, "chain_mode": chain_mode, "findings": findings,
    }
    digest = stable_digest(normalized)
    return {
        "artifact_id": f"immutability-report-{digest[:12]}", "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION, "lineage_id": f"sha256:{digest}",
        "artifact_count": len(current), "history_entry_count": len(history),
        "previous_release_entry_count": len(release), "checked_identity_count": checked,
        "finding_count": len(findings), "raw_overwrite_count": count("RAW_OVERWRITE"),
        "identity_reuse_count": count("IDENTITY_REUSE"), "schema_without_bump_count": count("SCHEMA_VERSION_NOT_BUMPED"),
        "historical_conflict_count": count("HISTORY_RELEASE_CONFLICT"),
        "current_hash_mismatch_count": count("CURRENT_HASH_MISMATCH"),
        "missing_current_hash_count": count("CURRENT_HASH_MISSING"), "missing_current_file_count": count("CURRENT_FILE_MISSING"),
        "immutable_removed_count": count("IMMUTABLE_ARTIFACT_REMOVED"),
        "append_only_truncation_count": count("APPEND_ONLY_HISTORY_TRUNCATED"),
        "mutability_violation_count": count("MUTABILITY_POLICY_VIOLATION"),
        "legacy_identity_count": count("LEGACY_PATH_IDENTITY"), "history_chain_failure_count": count("HISTORY_CHAIN_BROKEN"),
        "findings": findings, "status": "FAIL" if blocking else "PASS",
        "severity": "CRITICAL" if blocking else ("WARNING" if warning else "NONE"), "release_blocking": blocking,
        "no_raw_overwrite": count("RAW_OVERWRITE") == 0,
        "schema_change_requires_version_bump": count("SCHEMA_VERSION_NOT_BUMPED") == 0,
        "artifact_identity_stable": count("IDENTITY_REUSE") == 0,
        "immutable_artifacts_preserved": count("IMMUTABLE_ARTIFACT_REMOVED") == 0,
        "append_only_history_preserved": count("APPEND_ONLY_HISTORY_TRUNCATED") == 0,
        "history_chain_valid": chain_valid, "history_chain_mode": chain_mode, "genesis": genesis,
        "history_present": bool(history), "previous_release_present": bool(release), "paths_internal": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge", "promotion_blocked": True,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    required = ["artifact_manifest_all_phases", "hash_history", "release_manifest_previous"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    require_runtime_version(config)
    state = _load_state(inputs)
    current, history, release, genesis, chain_valid, chain_mode = state
    findings, checked = _collect_findings(current, history, release, genesis, chain_valid, chain_mode)
    artifact = _report(current, history, release, genesis, chain_valid, chain_mode, findings, checked, config)
    validate_output(artifact, "immutability_report.schema.yaml", "immutability_report")
    return {
        "module_id": "P0.S3.M04", "module_name": "artifact_immutability_checker", "phase": "P0",
        "subphase": "P0.S3", "contract": "P0_S3_M04_artifact_immutability_checker.yaml",
        "required_inputs": required, "outputs": {"immutability_report": artifact},
    }
