"""Publish S7 terminal-state artifacts and the S7-to-S8 manifest."""
from __future__ import annotations

from typing import Any

from ..artifacts import artifact_reference, sha256_value
from ..boundary.base import ArtifactEnvelope, HandoffManifestRecord
from ..boundary.config import S7Config
from ..subphases.s7_safety_diversity.rankability import RankabilityOutputs
from .runtime import artifact_from_records


def output_artifacts(bundle: Any, outputs: RankabilityOutputs, cfg: S7Config, module_id: str) -> list[ArtifactEnvelope]:
    base = bundle.manifest
    specs = (
        ("rankable_candidate_panel", outputs.rankable),
        ("abstained_candidate_panel", outputs.abstained),
        ("final_blocked_candidate_panel", outputs.blocked),
        ("rankability_group_report", outputs.group_reports),
    )
    return [
        artifact_from_records(
            name=name, schema_version="2.0.0", module_id=module_id,
            runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time,
            lineage_id=base.lineage_id, records=records,
        )
        for name, records in specs
    ]


def handoff_manifest(
    bundle: Any, outputs: RankabilityOutputs, artifacts: list[ArtifactEnvelope],
    score_env: ArtifactEnvelope, cluster_env: ArtifactEnvelope, cfg: S7Config, module_id: str,
) -> ArtifactEnvelope:
    passthrough = (
        "score_decomposition_panel", "comparison_group_panel",
        "validated_strategy_candidate_reference_panel",
    )
    references = [artifact_reference(item) for item in artifacts]
    references.extend(artifact_reference(bundle.artifacts[name]) for name in passthrough)
    references.extend((artifact_reference(score_env), artifact_reference(cluster_env)))
    conservation = sha256_value({
        "rankable": sorted(item.candidate_id for item in outputs.rankable),
        "abstained": sorted(item.candidate_id for item in outputs.abstained),
        "blocked": sorted(item.candidate_id for item in outputs.blocked),
    })
    record = HandoffManifestRecord(
        contract_id="p7_s7_to_s8_rankability_handoff", contract_version="2.0.0",
        producer=module_id, consumer="P7.S8",
        artifact_references=tuple(sorted(references, key=lambda item: item.artifact_name)),
        policy_versions={
            "similarity": cfg.similarity.policy_id, "diversity": cfg.diversity.policy_id,
            "safety": cfg.safety.policy_id, "abstention": cfg.abstention.policy_id,
        },
        candidate_count=len(bundle.candidates), forbidden_fields_scanned=True,
        candidate_conservation_sha256=conservation,
    )
    base = bundle.manifest
    return artifact_from_records(
        name="rankability_handoff_manifest", schema_version="2.0.0", module_id=module_id,
        runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time,
        lineage_id=base.lineage_id, records=(record,),
    )
