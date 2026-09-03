"""P7.S7.M01 — build sparse candidate similarity graph."""
from __future__ import annotations

from typing import Mapping

from ..application.reconciliation import load_scoring_bundle
from ..application.runtime import Timer, artifact_from_records, receipt
from ..boundary.config import S7Config
from ..subphases.s7_safety_diversity.similarity import build_similarity_graph

MODULE_ID = "P7.S7.M01"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S7Config.model_validate(config)
    bundle = load_scoring_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    edges, summaries, reasons = build_similarity_graph(bundle.candidates, cfg.similarity)
    base = bundle.manifest
    outputs = (
        artifact_from_records(name="candidate_similarity_edge_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=edges),
        artifact_from_records(name="candidate_similarity_summary_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=summaries),
    )
    module_receipt = receipt(module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, inputs=(base, *bundle.artifacts.values()), outputs=outputs, counts={"candidates": len(bundle.candidates), "edges": len(edges)}, reason_codes=reasons, policy_versions={"similarity": cfg.similarity.policy_id}, timer=timer)
    return {item.artifact_name: item.model_dump(mode="json") for item in outputs} | {"module_execution_receipt": module_receipt.model_dump(mode="json")}
