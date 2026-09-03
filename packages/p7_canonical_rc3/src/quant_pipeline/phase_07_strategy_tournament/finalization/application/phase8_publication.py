"""Build P8 execution-context and handoff artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..boundary.base import ArtifactEnvelope
from ..boundary.s8_config import S8Config
from ..boundary.s8_outputs import RankedStrategyRecord, ThesisCardRecord
from ..subphases.s8_publication.publication import build_publication_outputs, phase8_manifest_record
from .module_io import parse_envelope, parse_records
from .runtime import artifact_from_records


@dataclass(frozen=True, slots=True)
class PublicationInputs:
    ranked_env: ArtifactEnvelope
    thesis_env: ArtifactEnvelope
    audit_env: ArtifactEnvelope
    trace_env: ArtifactEnvelope
    tie_env: ArtifactEnvelope
    summary_env: ArtifactEnvelope
    ranked: tuple[RankedStrategyRecord, ...]


def load_publication_inputs(inputs: Mapping[str, object], module_id: str) -> PublicationInputs:
    names = (
        "ranked_strategy_candidate_panel", "strategy_thesis_card_panel", "ranking_audit_report",
        "ranking_trace_panel", "ranking_tie_report", "ranking_group_summary_panel",
    )
    envs = {name: parse_envelope(inputs, name, module_id) for name in names}
    ranked = parse_records(envs[names[0]], RankedStrategyRecord, module_id)
    parse_records(envs[names[1]], ThesisCardRecord, module_id)
    return PublicationInputs(
        envs[names[0]], envs[names[1]], envs[names[2]], envs[names[3]],
        envs[names[4]], envs[names[5]], ranked,
    )


def build_phase8_artifacts(bundle: Any, loaded: PublicationInputs, cfg: S8Config, module_id: str):
    decomposition = bundle.artifacts["score_decomposition_panel"]
    outputs = build_publication_outputs(
        loaded.ranked, dict(bundle.strategies), loaded.thesis_env, decomposition, cfg.publication
    )
    base = bundle.manifest
    build = lambda name, records: artifact_from_records(
        name=name, schema_version="2.0.0", module_id=module_id, runtime=cfg.runtime,
        cycle_id=base.cycle_id, decision_time=base.decision_time,
        lineage_id=base.lineage_id, records=records,
    )
    snapshot = build("ranked_strategy_execution_context_snapshot", outputs.snapshots)
    compatibility = build("compatibility_projection_report", outputs.legacy)
    published = (
        loaded.ranked_env, bundle.artifacts["abstained_candidate_panel"],
        bundle.artifacts["final_blocked_candidate_panel"], decomposition, loaded.thesis_env,
        loaded.trace_env, loaded.tie_env, loaded.summary_env, loaded.audit_env, snapshot, compatibility,
    )
    manifest_record = phase8_manifest_record(
        published, tuple(item.candidate_id for item in loaded.ranked),
        cfg.publication, cfg.runtime.run_timestamp, base.lineage_id,
    )
    manifest = build("phase8_strategy_ranking_handoff_manifest", (manifest_record,))
    return snapshot, compatibility, manifest
