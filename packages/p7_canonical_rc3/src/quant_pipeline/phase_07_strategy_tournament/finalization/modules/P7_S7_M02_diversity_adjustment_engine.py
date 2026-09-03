"""P7.S7.M02 — deterministic clusters and bounded diversity penalty."""
from __future__ import annotations

from collections import Counter
from typing import Mapping

from ..application.module_io import parse_envelope, parse_records
from ..application.reconciliation import load_scoring_bundle
from ..application.runtime import Timer, artifact_from_records, receipt
from ..boundary.config import S7Config
from ..boundary.outputs import AuditRecord, SimilarityEdgeRecord
from ..subphases.s7_safety_diversity.diversity import adjust_diversity

MODULE_ID = "P7.S7.M02"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S7Config.model_validate(config)
    bundle = load_scoring_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    edge_envelope = parse_envelope(inputs, "candidate_similarity_edge_panel", MODULE_ID)
    edges = parse_records(edge_envelope, SimilarityEdgeRecord, MODULE_ID)
    clusters, adjustments, adjusted_scores = adjust_diversity(bundle.candidates, edges, cfg.diversity)
    base = bundle.manifest
    audit = AuditRecord(cycle_id=base.cycle_id, decision_time=base.decision_time, module_id=MODULE_ID, counts={"candidates": len(bundle.candidates), "clusters": len(set(item.diversity_cluster_id for item in clusters)), "edges": len(edges)}, reason_code_distribution={}, policy_version=cfg.diversity.policy_id, lineage_id=base.lineage_id)
    outputs = (
        artifact_from_records(name="candidate_diversity_cluster_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=clusters),
        artifact_from_records(name="diversity_adjustment_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=adjustments),
        artifact_from_records(name="diversity_adjusted_score_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=adjusted_scores),
        artifact_from_records(name="diversity_audit_report", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=(audit,)),
    )
    module_receipt = receipt(module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, inputs=(base, edge_envelope), outputs=outputs, counts=audit.counts, reason_codes=(), policy_versions={"diversity": cfg.diversity.policy_id}, timer=timer)
    return {item.artifact_name: item.model_dump(mode="json") for item in outputs} | {"module_execution_receipt": module_receipt.model_dump(mode="json")}
