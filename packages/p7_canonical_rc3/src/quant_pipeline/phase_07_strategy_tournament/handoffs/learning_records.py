from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from ..errors import P7ContractError
from ..learning.feature_spec import FEATURE_NAMES
from .common import artifact_records, candidate_index, parse_timestamp
HANDOFF_MODULE_ID = "P7.HANDOFF.TOURNAMENT_TO_LEARNING"


def _metric_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    result: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in rows:
        candidate_id = str(row["candidate_id"])
        metric_id = str(row["metric_id"])
        raw_value = row.get("adjusted_directed_value", row.get("directed_value"))
        result[candidate_id][metric_id] = float(raw_value) if raw_value is not None else None
    return result


def _first_available(metrics: Mapping[str, float | None], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = metrics.get(name)
        if value is not None:
            return float(value)
    return None


def _feature_rows(
    groups: list[dict[str, Any]],
    eligible: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    *,
    feature_schema_hash: str,
    feature_available_at: str,
) -> list[dict[str, Any]]:
    group_index = candidate_index(groups, "candidate_comparison_group_panel")
    eligible_index = candidate_index(eligible, "eligible_strategy_candidate_panel")
    metrics = _metric_map(factor_rows)
    rows = []
    for candidate_id, group in sorted(group_index.items()):
        values = metrics.get(candidate_id, {})
        edge = _first_available(values, ("expected_net_payoff",))
        risk_raw = _first_available(values, ("expected_shortfall", "maximum_loss"))
        eligible_record = eligible_index[candidate_id]
        feature_base = eligible_record.get("feature_base") or {}
        cost_liquidity = eligible_record.get("cost_liquidity") or {}
        risk_record = eligible_record.get("risk") or {}
        entry_cost = cost_liquidity.get("entry_cost")
        maximum_loss = risk_record.get("maximum_loss")
        cost_quality = None
        if entry_cost is not None and maximum_loss is not None and abs(float(maximum_loss)) > 1e-12:
            cost_ratio = abs(float(entry_cost)) / abs(float(maximum_loss))
            cost_quality = max(0.0, 1.0 - min(1.0, cost_ratio))
        elif entry_cost is not None:
            cost_quality = 1.0 / (1.0 + abs(float(entry_cost)))
        fit_raw = _first_available(values, ("payoff_fit_error",))
        risk = abs(risk_raw) if risk_raw is not None else None
        robustness = max(0.0, 1.0 - min(1.0, abs(fit_raw))) if fit_raw is not None else None
        rows.append(
            {
                "candidate_id": candidate_id,
                "comparison_group_id": str(group["comparison_group_id"]),
                "underlying_id": str(group["underlying_id"]),
                "horizon": str(group["horizon"]),
                "objective_family": str(group["objective_family"]),
                "capital_at_risk_bucket": str(group["capital_at_risk_bucket"]),
                "feature_schema_hash": feature_schema_hash,
                "feature_available_at": feature_available_at,
                "feature_values": {
                    "cost_quality": cost_quality,
                    "edge_signal": edge,
                    "risk_penalty": risk,
                    "robustness": robustness,
                },
                "data_quality_score": feature_base.get(
                    "data_quality_score", eligible_index[candidate_id].get("data_quality_score")
                ),
                "ood_score": feature_base.get(
                    "ood_score", eligible_index[candidate_id].get("ood_score")
                ),
                "lineage_id": str(eligible_index[candidate_id].get("lineage_id")),
            }
        )
    return rows


def _pareto_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        frontier_status = row.get("frontier_status")
        status = "SURVIVOR" if frontier_status in {"FRONTIER", "DOMINATED_LAYER"} else "INCOMPARABLE"
        result.append(
            {
                "candidate_id": str(row["candidate_id"]),
                "comparison_group_id": str(row["comparison_group_id"]),
                "pareto_status": status,
            }
        )
    return result


def _score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": str(row["candidate_id"]),
            "comparison_group_id": str(row["comparison_group_id"]),
            "interpretable_score": float(row["final_interpretable_score"]),
            "scale_id": "realized_net_utility_v1",
            "score_status": "VALID" if row.get("score_status") == "AVAILABLE" else str(row.get("score_status")),
        }
        for row in rows
    ]


def _decomposition_rows(
    rows: list[dict[str, Any]],
    group_index: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    stages: dict[str, dict[str, float]] = defaultdict(dict)
    lineage: dict[str, str] = {}
    for row in rows:
        candidate_id = str(row["candidate_id"])
        lineage[candidate_id] = str(row.get("lineage_id", f"lineage:{candidate_id}"))
        if row.get("stage_type") == "HEAD":
            stage_id = str(row.get("head_id", row.get("stage_id")))
            stages[candidate_id][stage_id] = float(row.get("score_contribution", 0.0))
    return [
        {
            "candidate_id": candidate_id,
            "comparison_group_id": str(group_index[candidate_id]["comparison_group_id"]),
            "stages": dict(sorted(stages[candidate_id].items())),
            "formula_version": "tournament-v2.2",
            "lineage_id": lineage.get(candidate_id, f"lineage:{candidate_id}"),
        }
        for candidate_id in sorted(group_index)
    ]


def _group_registry(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        group_id = str(group["comparison_group_id"])
        if group_id in seen:
            continue
        seen.add(group_id)
        result.append(
            {
                "comparison_group_id": group_id,
                "underlying_id": str(group["underlying_id"]),
                "horizon": str(group["horizon"]),
                "objective_family": str(group["objective_family"]),
                "capital_at_risk_bucket": str(group["capital_at_risk_bucket"]),
            }
        )
    return result
