from __future__ import annotations

from typing import Any, Mapping

from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import content_hash, model_or_mapping
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.replay.models import (
    ArtifactRef,
    RetroPolicyPatchView,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.memory.models import (
    Phase3RunSnapshotView as MemoryRunSnapshotView,
    PersonSchemaPolicyView as MemoryPersonSchemaPolicyView,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.warmup_memory.history.models import (
    Phase3RunSnapshotView as HistoryRunSnapshotView,
)


def _snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, object]:
    source = model_or_mapping(snapshot)
    identity = source["identity"]
    temporal = source["temporal"]
    return {
        "schema_id": "phase3_run_snapshot.v1",
        "schema_version": source.get("schema_version", "2.0.0"),
        "run_id": identity["run_id"],
        "snapshot_id": identity["snapshot_id"],
        "as_of": temporal["as_of"],
        "evaluation_start": temporal.get("evaluation_start"),
        "evaluation_end": temporal.get("evaluation_end"),
        "lineage_id": source["lineage_id"],
        "snapshot_hash": source["snapshot_hash"],
    }


def to_history_snapshot_view(snapshot: Mapping[str, Any]) -> HistoryRunSnapshotView:
    """Project governance snapshot into S9 without changing governance authority's canonical artifact."""

    return HistoryRunSnapshotView.model_validate(_snapshot_payload(snapshot), strict=True)


def to_memory_snapshot_view(snapshot: Mapping[str, Any]) -> MemoryRunSnapshotView:
    """Project governance snapshot into S14's strict bootstrap view."""

    return MemoryRunSnapshotView.model_validate(_snapshot_payload(snapshot), strict=True)


def _policy_ref(patch: Mapping[str, Any]) -> ArtifactRef:
    target = str(patch["change_target"])
    return ArtifactRef(
        artifact_id=str(patch["patch_id"]),
        artifact_type=target,
        content_hash=str(patch["payload_hash"]),
        schema_id=f"{target}.v1",
        schema_version=str(patch.get("target_current_version", "1.0.0")),
    )


def to_warmup_retro_patch(
    active_patch: Mapping[str, Any],
) -> RetroPolicyPatchView:
    """Convert governance promoted patch semantics into warm-up's warm-up view.

    No-patch is represented explicitly. Active patches preserve the promoted payload hash and
    are exposed only through the matching prompt/retrieval/tool reference.
    """

    source = model_or_mapping(active_patch)
    status = source["status"]
    patch = source.get("patch")
    common: dict[str, object] = {
        "schema_id": "active_retro_policy_patch.v2",
        "schema_version": "2.0.0",
        "artifact_id": f"active-retro-{source['content_hash'][:24]}",
        "run_id": source["run_id"],
        "snapshot_id": source["snapshot_id"],
        "patch_hash": source["content_hash"],
        "lineage_id": source["lineage_id"],
    }
    if status == "NO_PATCH" or patch is None:
        common["status"] = "NO_PATCH"
        return RetroPolicyPatchView.model_validate(common, strict=True)
    if status not in {"ACTIVE", "VALID_PATCH"}:
        raise ValueError(f"governance patch status is not consumable by warm-up: {status}")
    ref = _policy_ref(patch)
    target = patch["change_target"]
    common.update({"status": "VALID_PATCH", "effective_from": patch.get("promoted_at")})
    if target == "prompt_policy":
        common["prompt_policy_ref"] = ref
    elif target == "retrieval_policy":
        common["retrieval_policy_ref"] = ref
    elif target == "tool_policy":
        common["tool_policy_ref"] = ref
    else:
        raise ValueError(f"Unsupported promoted change_target: {target}")
    return RetroPolicyPatchView.model_validate(common, strict=True)


def to_memory_person_policy_view(person_schema_policy: Mapping[str, Any]) -> MemoryPersonSchemaPolicyView:
    """Project governance authority's canonical person authority into S14's memory ontology view.

    The four memory types and four visibility scopes are foundation shared-contract constants;
    they are not inferred from provider data or generated at runtime.
    """
    source = model_or_mapping(person_schema_policy)
    return MemoryPersonSchemaPolicyView(
        policy_id=str(source["policy_id"]),
        person_schema_version=str(source["person_profile_schema"]["schema_version"]),
        allowed_memory_types=("EPISODIC", "SEMANTIC", "PROCEDURAL", "SOCIAL"),
        allowed_visibility_scopes=("SELF", "SOCIAL_VISIBLE", "PUBLIC", "AUDIT_ONLY"),
        content_hash=str(source["policy_hash"]),
        lineage_id=str(source["lineage_id"]),
    )
