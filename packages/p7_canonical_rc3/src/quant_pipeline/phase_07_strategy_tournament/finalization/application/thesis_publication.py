"""Build thesis, trace and audit artifacts for ranked strategies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..boundary.base import ArtifactEnvelope
from ..boundary.s8_config import S8Config
from ..boundary.s8_outputs import RankedStrategyRecord, RankingAuditRecord, RankingGroupSummaryRecord, RankingTieRecord
from ..subphases.s8_publication.thesis import build_thesis_outputs
from .module_io import parse_envelope, parse_records
from .runtime import artifact_from_records


@dataclass(frozen=True, slots=True)
class RankingInputs:
    ranked_env: ArtifactEnvelope
    tie_env: ArtifactEnvelope
    summary_env: ArtifactEnvelope
    ranked: tuple[RankedStrategyRecord, ...]
    ties: tuple[RankingTieRecord, ...]
    summaries: tuple[RankingGroupSummaryRecord, ...]


def load_ranking_inputs(inputs: Mapping[str, object], module_id: str) -> RankingInputs:
    names = ("ranked_strategy_candidate_panel", "ranking_tie_report", "ranking_group_summary_panel")
    envs = {name: parse_envelope(inputs, name, module_id) for name in names}
    return RankingInputs(
        envs[names[0]], envs[names[1]], envs[names[2]],
        parse_records(envs[names[0]], RankedStrategyRecord, module_id),
        parse_records(envs[names[1]], RankingTieRecord, module_id),
        parse_records(envs[names[2]], RankingGroupSummaryRecord, module_id),
    )


def build_thesis_artifacts(bundle: Any, loaded: RankingInputs, cfg: S8Config, module_id: str):
    evidence_ids = tuple(sorted({
        loaded.ranked_env.artifact_id,
        bundle.artifacts["score_decomposition_panel"].artifact_id,
        bundle.artifacts["validated_strategy_candidate_reference_panel"].artifact_id,
    }))
    outputs = build_thesis_outputs(
        loaded.ranked, dict(bundle.strategies), dict(bundle.decomposition),
        cfg.ranking, cfg.thesis, evidence_ids,
    )
    base = bundle.manifest
    build = lambda name, records: artifact_from_records(
        name=name, schema_version="2.0.0", module_id=module_id, runtime=cfg.runtime,
        cycle_id=base.cycle_id, decision_time=base.decision_time,
        lineage_id=base.lineage_id, records=records,
    )
    return build("strategy_thesis_card_panel", outputs.cards), build("ranking_trace_panel", outputs.traces)


def build_audit_record(
    bundle: Any, loaded: RankingInputs, input_envs: tuple[ArtifactEnvelope, ...],
    output_envs: tuple[ArtifactEnvelope, ...], cfg: S8Config,
) -> RankingAuditRecord:
    return RankingAuditRecord(
        run_id=cfg.runtime.run_id, cycle_id=bundle.manifest.cycle_id,
        decision_time=bundle.manifest.decision_time, received_count=bundle.manifest_record.candidate_count,
        ranked_count=len(loaded.ranked), abstained_count=len(bundle.abstained), blocked_count=len(bundle.blocked),
        candidate_conservation_pass=True, group_count=len(loaded.summaries), tie_count=len(loaded.ties),
        policy_versions={**bundle.manifest_record.policy_versions, "ranking": cfg.ranking.policy_id,
                         "thesis": cfg.thesis.policy_id},
        model_versions=tuple(sorted({item.model_id for item in loaded.ranked})),
        input_artifact_hashes={item.artifact_name: item.content_sha256 for item in input_envs},
        output_artifact_hashes={item.artifact_name: item.content_sha256 for item in output_envs},
        lineage_id=bundle.manifest.lineage_id,
    )
