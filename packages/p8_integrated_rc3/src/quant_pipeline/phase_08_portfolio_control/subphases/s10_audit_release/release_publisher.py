from __future__ import annotations
import hashlib
from pathlib import Path
from .errors import ReleaseIntegrityError
from .models_common import content_sha256
from .models_release import (FileHashEntry, P0QualificationHandoff, ReleaseManifest,
    ReleasePublicationRequest, ReleasePublicationResult)

def _safe_file(root: Path, relative: str) -> Path:
    candidate = (root/relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleaseIntegrityError(f"file outside release root: {relative}") from exc
    if not candidate.is_file():
        raise ReleaseIntegrityError(f"release file does not exist: {relative}")
    return candidate

def _file_entries(request: ReleasePublicationRequest) -> tuple[FileHashEntry, ...]:
    root = Path(request.release_root)
    unique = sorted(set(request.included_paths))
    if len(unique) != len(request.included_paths):
        raise ReleaseIntegrityError("included_paths contains duplicates")
    entries = []
    for relative in unique:
        path = _safe_file(root, relative)
        data = path.read_bytes()
        entries.append(FileHashEntry(relative_path=relative, size_bytes=len(data),
                                     sha256=hashlib.sha256(data).hexdigest()))
    return tuple(entries)

def _validate_evidence(request: ReleasePublicationRequest) -> None:
    item = request.evidence
    required = (
        item.tests_passed > 0 and item.tests_failed == 0 and item.combined_coverage_percent >= 80.0
        and item.structure_gate_passed and item.clean_install_passed
        and item.clean_extraction_passed and item.deterministic_replay_passed
        and item.p9_consumer_passed and item.namespace_coexistence_passed
    )
    if not required:
        raise ReleaseIntegrityError("release evidence is incomplete, below coverage threshold, or contains failures")
    if request.qualification.context != request.context or request.p9_handoff.context != request.context:
        raise ReleaseIntegrityError("release qualification/handoff context mismatch")
    qualification_hash = content_sha256(request.qualification)
    handoff_hash = content_sha256(request.p9_handoff)
    if request.qualification_ref.content_sha256 != qualification_hash or request.qualification_ref.producer_module != "P8.S10.M02":
        raise ReleaseIntegrityError("qualification reference is not authenticated")
    if request.p9_handoff_ref.content_sha256 != handoff_hash or request.p9_handoff_ref.producer_module != "P8.S10.M03":
        raise ReleaseIntegrityError("P9 handoff reference is not authenticated")

def publish_release(request: ReleasePublicationRequest) -> ReleasePublicationResult:
    _validate_evidence(request)
    entries = _file_entries(request)
    manifest_digest = content_sha256([entry.model_dump(mode="json") for entry in entries])
    release_id = "rel_" + hashlib.sha256(
        f"{request.package_name}|{request.package_version}|{manifest_digest}".encode()).hexdigest()[:20]
    manifest = ReleaseManifest(release_id=release_id, package_name=request.package_name,
        package_version=request.package_version, sealed_at=request.sealed_at, files=entries,
        manifest_sha256=manifest_digest, qualification_ref=request.qualification_ref,
        p9_handoff=request.p9_handoff, p9_handoff_ref=request.p9_handoff_ref,
        known_debts=request.known_debts)
    handoff_id = "p0h_" + hashlib.sha256(f"{release_id}|{manifest_digest}".encode()).hexdigest()[:20]
    p0 = P0QualificationHandoff(handoff_id=handoff_id, context=request.context,
        release_id=release_id, qualification=request.qualification, evidence=request.evidence,
        manifest_sha256=manifest_digest, dependency_components=request.dependency_components,
        production_promotion_allowed=False)
    return ReleasePublicationResult(manifest=manifest, p0_handoff=p0)
