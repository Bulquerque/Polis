"""Build validated P6 strategy references for S7-S8."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..canonical import digest
from ..errors import P7ContractError
from .common import artifact_records


def p6_artifact_map(foundation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index = foundation.get("verified_p6_artifact_index")
    if not isinstance(index, Mapping):
        raise P7ContractError(
            "P7_HANDOFF_P6_INDEX_MISSING",
            "verified_p6_artifact_index is required to preserve source references",
        )
    records = artifact_records(index, "verified_p6_artifact_index")
    if len(records) != 1 or not isinstance(records[0].get("artifacts"), list):
        raise P7ContractError(
            "P7_HANDOFF_P6_INDEX_INVALID",
            "verified_p6_artifact_index must contain one artifacts list",
        )
    return _index_artifact_references(records[0]["artifacts"])


def _index_artifact_references(rows: list[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for artifact in rows:
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("artifact_name"), str):
            raise P7ContractError("P7_HANDOFF_P6_INDEX_INVALID", "invalid P6 artifact reference")
        result[str(artifact["artifact_name"])] = dict(artifact)
    return result


def source_reference_fields(p6_artifacts: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    from ..finalization.boundary.base import ArtifactReference

    mapping = {
        "strategy_candidate_reference": "strategy_candidate_panel",
        "strategy_legs_reference": "strategy_leg_panel",
        "payoff_evaluation_reference": "strategy_payoff_panel",
        "scenario_evaluation_reference": "strategy_scenario_evaluation_panel",
        "risk_reference": "strategy_risk_panel",
        "cost_liquidity_reference": "strategy_cost_liquidity_panel",
        "greeks_reference": "strategy_greek_panel",
        "generation_trace_reference": "strategy_generation_trace_panel",
    }
    return {
        field: ArtifactReference(
            artifact_name=artifact_name,
            artifact_id=str(source["artifact_id"]),
            content_sha256=str(source["content_sha256"]),
            schema_version=str(source["schema_version"]),
            record_count=int(source["record_count"]),
        )
        for field, artifact_name in mapping.items()
        if (source := p6_artifacts.get(artifact_name)) is not None
    }


def _float_tuple(values: Any) -> tuple[float, ...]:
    return tuple(float(value) for value in values or ())


def _scenario_payoff(base: Mapping[str, Any]) -> tuple[float, ...]:
    return tuple(
        float(row["scenario_payoff"])
        for row in base.get("scenario_evaluations", ())
        if isinstance(row, Mapping) and row.get("scenario_payoff") is not None
    )


def _greek_vector(base: Mapping[str, Any]) -> tuple[float, ...]:
    rows = base.get("greeks", ())
    if not rows or not isinstance(rows[0], Mapping):
        return ()
    return tuple(
        float(rows[0][name])
        for name in ("delta", "gamma", "vega", "theta")
        if rows[0].get(name) is not None
    )


def _expiration_ids(base: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({
        str(leg["expiration"])
        for leg in base.get("legs", ())
        if isinstance(leg, Mapping) and leg.get("expiration") is not None
    }))


def _leg_ids(base: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(leg["leg_id"])
        for leg in base.get("legs", ())
        if isinstance(leg, Mapping) and leg.get("leg_id")
    )


def _mutation_trace(base: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(trace["trace_id"])
        for trace in base.get("generation_trace", ())
        if isinstance(trace, Mapping) and trace.get("trace_id")
    )


def _strategy_record(
    score_row: Mapping[str, Any], base: Mapping[str, Any], group: Mapping[str, Any],
    pareto_row: Mapping[str, Any], candidate_artifact: Mapping[str, Any],
    source_references: Mapping[str, Any], *, cycle_id: str, decision_time: Any,
):
    from ..finalization.boundary.inputs import StrategyReferenceRecord

    candidate_id = str(score_row["candidate_id"])
    candidate = dict(base.get("candidate", {}))
    return StrategyReferenceRecord(
        cycle_id=cycle_id, decision_time=decision_time, candidate_id=candidate_id,
        comparison_group_id=str(group["comparison_group_id"]),
        candidate_identity_hash=digest(candidate), strategy_artifact_id=str(candidate_artifact["artifact_id"]),
        strategy_content_sha256=str(candidate_artifact["content_sha256"]),
        strategy_schema_version=str(candidate_artifact["schema_version"]),
        strategy_lineage_id=str(base.get("lineage_id")), payoff_shape=_float_tuple(base.get("payoff_shape")),
        scenario_payoff=_scenario_payoff(base), greek_vector=_greek_vector(base), leg_ids=_leg_ids(base),
        origin_template=str(candidate.get("strategy_class")) if candidate.get("strategy_class") else None,
        expiration_ids=_expiration_ids(base),
        defined_risk_status="VALID" if base.get("risk", {}).get("maximum_loss_proven") is True else "UNPROVEN",
        execution_context_time=decision_time, context_available=True,
        pareto_tier=0 if pareto_row.get("pareto_status") == "SURVIVOR" else 1,
        belief_reference_ids=tuple(candidate.get("belief_reference_ids", ())),
        mutation_trace=_mutation_trace(base), profit_regions=tuple(base.get("profit_regions", ())),
        failure_regions=tuple(base.get("failure_regions", ())),
        invalidation_conditions=tuple(base.get("invalidation_conditions", ())), **source_references,
    )


def build_strategy_records(
    score_rows: list[dict[str, Any]], eligible: Mapping[str, dict[str, Any]],
    groups: Mapping[str, dict[str, Any]], pareto: Mapping[str, dict[str, Any]],
    p6_artifacts: Mapping[str, dict[str, Any]], *, cycle_id: str, decision_time: Any,
) -> list[Any]:
    candidate_artifact = p6_artifacts.get("strategy_candidate_panel")
    if candidate_artifact is None:
        raise P7ContractError(
            "P7_HANDOFF_STRATEGY_REFERENCE_MISSING", "strategy_candidate_panel reference is required"
        )
    references = source_reference_fields(p6_artifacts)
    return [
        _strategy_record(
            row, eligible[str(row["candidate_id"])], groups[str(row["candidate_id"])],
            pareto.get(str(row["candidate_id"]), {}), candidate_artifact, references,
            cycle_id=cycle_id, decision_time=decision_time,
        )
        for row in score_rows
    ]
