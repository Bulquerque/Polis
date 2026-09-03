"""P7.S8.M01 — deterministic ranking inside comparison groups."""
from __future__ import annotations

from typing import Mapping

from ..application.runtime import Timer, artifact_from_records, receipt
from ..application.s8_reconciliation import load_s8_bundle
from ..boundary.s8_config import S8Config
from ..domain.s8_models import RankingCandidate
from ..subphases.s8_publication.ranking import rank_candidates

MODULE_ID = "P7.S8.M01"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S8Config.model_validate(config)
    bundle = load_s8_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    candidates = tuple(
        RankingCandidate(row, bundle.groups[row.candidate_id], bundle.strategies[row.candidate_id], bundle.clusters[row.candidate_id])
        for row in bundle.rankable
    )
    outputs = rank_candidates(candidates, cfg.ranking)
    base = bundle.manifest
    specs = (
        ("ranked_strategy_candidate_panel", outputs.ranked),
        ("ranking_tie_report", outputs.ties),
        ("ranking_group_summary_panel", outputs.groups),
    )
    artifacts = [
        artifact_from_records(
            name=name,
            schema_version="2.0.0",
            module_id=MODULE_ID,
            runtime=cfg.runtime,
            cycle_id=base.cycle_id,
            decision_time=base.decision_time,
            lineage_id=base.lineage_id,
            records=records,
        )
        for name, records in specs
    ]
    module_receipt = receipt(
        module_id=MODULE_ID,
        runtime=cfg.runtime,
        cycle_id=base.cycle_id,
        inputs=(base, *bundle.artifacts.values()),
        outputs=artifacts,
        counts={"rankable": len(bundle.rankable), "ranked": len(outputs.ranked), "ties": len(outputs.ties)},
        reason_codes=("P7_RANKING_TIE_REPORTED" for _ in outputs.ties),
        policy_versions={"ranking": cfg.ranking.policy_id},
        timer=timer,
    )
    return {item.artifact_name: item.model_dump(mode="json") for item in artifacts} | {
        "module_execution_receipt": module_receipt.model_dump(mode="json")
    }
