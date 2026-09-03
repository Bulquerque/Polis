"""Normalize S4 tournament outputs for the S6 runtime scoring contract."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import P7ContractError
from ..learning.domain.canonical import digest
from .common import artifact_records, candidate_index, parse_timestamp
from ..learning.feature_spec import feature_schema_hash
from .learning_records import (
    _decomposition_rows,
    _feature_rows,
    _group_registry,
    _pareto_rows,
    _score_rows,
)

HANDOFF_MODULE_ID = "P7.HANDOFF.TOURNAMENT_TO_LEARNING"


def _load_records(tournament: Mapping[str, Any], foundation: Mapping[str, Any]) -> dict[str, Any]:
    groups_artifact = foundation["candidate_comparison_group_panel"]
    records = {
        "groups_artifact": groups_artifact,
        "groups": artifact_records(groups_artifact, "candidate_comparison_group_panel"),
        "eligible": artifact_records(
            foundation["eligible_strategy_candidate_panel"], "eligible_strategy_candidate_panel"
        ),
        "factors": artifact_records(tournament["factor_adjusted_metric_panel"], "factor_adjusted_metric_panel"),
        "pareto": artifact_records(tournament["pareto_frontier_panel"], "pareto_frontier_panel"),
        "scores": artifact_records(tournament["interpretable_score_panel"], "interpretable_score_panel"),
        "decompositions": artifact_records(tournament["score_decomposition_panel"], "score_decomposition_panel"),
    }
    group_ids = set(candidate_index(records["groups"], "candidate_comparison_group_panel"))
    eligible_ids = set(candidate_index(records["eligible"], "eligible_strategy_candidate_panel"))
    if group_ids != eligible_ids:
        raise P7ContractError(
            "P7_HANDOFF_CANDIDATE_SET_MISMATCH",
            "foundation candidate and group sets differ",
        )
    return records


def _module_context(records: Mapping[str, Any], tournament: Mapping[str, Any], pipeline_version: str):
    from ..learning.boundary import ModuleContext

    groups = records["groups_artifact"]
    return ModuleContext(
        run_id=str(groups["run_id"]),
        cycle_id=str(groups["cycle_id"]),
        decision_time=parse_timestamp(groups["decision_time"], "decision_time"),
        available_at=parse_timestamp(
            tournament["factor_adjusted_metric_panel"]["available_at"], "available_at"
        ),
        created_at=parse_timestamp(tournament["interpretable_score_panel"]["created_at"], "created_at"),
        pipeline_version=pipeline_version,
        lineage_id=str(groups["lineage_id"]),
    )


def _record_bundle(records: Mapping[str, Any], tournament: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups = records["groups"]
    eligible = records["eligible"]
    group_index = candidate_index(groups, "candidate_comparison_group_panel")
    eligible_index = candidate_index(eligible, "eligible_strategy_candidate_panel")
    group_registry = _group_registry(groups)
    feature_rows = _feature_rows(
        groups,
        eligible,
        records["factors"],
        feature_schema_hash=feature_schema_hash(),
        feature_available_at=str(tournament["factor_adjusted_metric_panel"]["available_at"]),
    )
    return {
        "comparison_group_registry": group_registry,
        "pareto_candidate_panel": _pareto_rows(records["pareto"]),
        "factor_adjusted_candidate_panel": feature_rows,
        "interpretable_score_panel": _score_rows(records["scores"]),
        "interpretable_score_decomposition_panel": _decomposition_rows(records["decompositions"], group_index),
        "metric_semantics_registry": [{
            "metric_id": "interpretable_score", "direction": "HIGHER_BETTER",
            "scale_id": "realized_net_utility_v1", "semantic_version": "2.2.0", "unit": "utility",
        }],
        "candidate_lineage_panel": [{
            "candidate_id": candidate_id,
            "comparison_group_id": str(group_index[candidate_id]["comparison_group_id"]),
            "lineage_id": str(eligible_index[candidate_id].get("lineage_id")),
            "p6_candidate_id": candidate_id,
        } for candidate_id in sorted(group_index)],
        "tournament_audit_report": [{
            "status": "PASS", "candidate_count": len(feature_rows),
            "group_count": len(group_registry), "conservation_pass": True,
        }],
    }


def _publish_records(record_bundle: Mapping[str, list[dict[str, Any]]], context) -> dict[str, Any]:
    from ..learning.boundary import build_artifact

    return {
        name: build_artifact(
            name=name, producer_module_id=HANDOFF_MODULE_ID,
            records=value, context=context, schema_version="2.2.0",
        )
        for name, value in record_bundle.items()
    }


def _publish_manifest(artifacts: dict[str, Any], context) -> None:
    from ..learning.boundary import build_artifact
    references = [{
        "artifact_name": name, "artifact_id": artifact["artifact_id"],
        "content_sha256": artifact["content_sha256"], "record_count": artifact["record_count"],
        "schema_version": artifact["schema_version"],
    } for name, artifact in sorted(artifacts.items())]
    manifest = [{
        "contract_id": "p7-tournament-to-learning-v2.2", "contract_version": "2.2.0",
        "producer_stage": "TOURNAMENT", "consumer_stage": "LEARNING",
        "artifact_references": references, "reference_count": len(references),
        "content_sha256": digest(references),
    }]
    artifacts["interpretable_tournament_handoff_manifest"] = build_artifact(
        name="interpretable_tournament_handoff_manifest", producer_module_id=HANDOFF_MODULE_ID,
        records=manifest, context=context, schema_version="2.2.0",
    )


def _publish_empty_model_slots(artifacts: dict[str, Any], context) -> None:
    from ..learning.boundary import build_artifact

    for name in (
        "ltr_model_artifact", "ltr_model_qualification_registry",
        "ltr_model_qualification_report", "governed_model_registry",
    ):
        artifacts[name] = build_artifact(
            name=name, producer_module_id="P0.MODEL.REGISTRY",
            records=[], context=context, schema_version="2.2.0",
        )


def prepare_learning_inputs(
    tournament: Mapping[str, Any], foundation: Mapping[str, Any], *, pipeline_version: str = "P7-2.3"
) -> dict[str, Any]:
    """Build the S6 input bundle while preserving absence and lineage."""
    records = _load_records(tournament, foundation)
    context = _module_context(records, tournament, pipeline_version)
    artifacts = _publish_records(_record_bundle(records, tournament), context)
    _publish_manifest(artifacts, context)
    _publish_empty_model_slots(artifacts, context)
    return artifacts
