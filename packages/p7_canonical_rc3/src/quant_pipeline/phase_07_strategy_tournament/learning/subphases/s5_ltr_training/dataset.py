from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from ...domain.canonical import iso_utc
from ...feature_spec import feature_schema_hash
from ...domain.errors import fail
from ...domain.models import Transformation

Key = tuple[str, str]


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    query_id: str
    cycle_id: str
    decision_time: datetime
    feature_available_at: datetime
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    feature_schema_version: str
    features: dict[str, float | None]
    interpretable_score: float
    selected_by_p8: bool
    candidate_topology: str
    regime: str | None = None
    lineage_id: str

    @field_validator("decision_time", "feature_available_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class OutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    query_id: str
    source_cycle_id: str
    target_id: str
    outcome_value: float
    outcome_available_at: datetime
    label_end_time: datetime
    costs_included: bool
    denominator: str
    lineage_id: str

    @field_validator("outcome_available_at", "label_end_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class DatasetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    target_id: str
    training_cutoff_at: datetime
    min_query_coverage: float = 1.0
    min_overall_coverage: float = 0.95
    minimum_candidates_per_query: int = 2
    require_nonselected_counterfactuals: bool = True
    allowed_feature_names: tuple[str, ...] = ()

    @field_validator("min_query_coverage", "min_overall_coverage")
    @classmethod
    def coverage_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("coverage must be in [0,1]")
        return value


def _policy_record(records: tuple[dict[str, Any], ...], target_id: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("target_id") == target_id]
    if len(matches) != 1:
        fail("P7_LTR_TARGET_POLICY_INVALID", f"target policy {target_id} not uniquely resolved")
    return matches[0]


def _parse_snapshots(
    records: tuple[dict[str, Any], ...], policy: DatasetPolicy, current_cycle_id: str
) -> dict[Key, SnapshotRecord]:
    result: dict[Key, SnapshotRecord] = {}
    for raw in records:
        item = SnapshotRecord.model_validate(raw)
        key = (item.query_id, item.candidate_id)
        if key in result:
            fail("P7_LTR_QUERY_GROUP_INVALID", f"duplicate historical candidate {key}")
        if item.cycle_id == current_cycle_id:
            fail("P7_LTR_CURRENT_CYCLE_OUTCOME", "current-cycle snapshots cannot enter offline training")
        if item.feature_available_at > item.decision_time:
            fail("P7_LTR_FEATURE_FUTURE_DATED", "feature availability exceeds decision time")
        if item.decision_time > policy.training_cutoff_at:
            fail("P7_LTR_SNAPSHOT_AFTER_TRAINING_CUTOFF", "snapshot decision time exceeds training cutoff")
        unknown = sorted(set(item.features) - set(policy.allowed_feature_names)) if policy.allowed_feature_names else []
        if unknown:
            fail("P7_LTR_FEATURE_SCHEMA_MISMATCH", f"unknown feature names: {unknown}")
        result[key] = item
    return result


def _validate_outcome(
    item: OutcomeRecord, snapshot: SnapshotRecord, policy: DatasetPolicy, target: Mapping[str, Any]
) -> None:
    if item.source_cycle_id != snapshot.cycle_id:
        fail("P7_LTR_QUERY_GROUP_INVALID", "outcome source cycle does not match snapshot cycle")
    if item.label_end_time < snapshot.decision_time:
        fail("P7_LTR_OUTCOME_TEMPORAL_ORDER_INVALID", "label end precedes decision time")
    if item.outcome_available_at < item.label_end_time:
        fail("P7_LTR_OUTCOME_TEMPORAL_ORDER_INVALID", "outcome is available before label completion")
    if item.label_end_time > policy.training_cutoff_at or item.outcome_available_at > policy.training_cutoff_at:
        fail("P7_LTR_OUTCOME_FUTURE_DATED", "label or outcome exceeds training cutoff")
    if item.costs_included != bool(target["costs_included"]) or item.denominator != str(target["denominator"]):
        fail("P7_LTR_TARGET_UNIT_MISMATCH", "target economic semantics mismatch")


def _parse_outcomes(
    records: tuple[dict[str, Any], ...], snapshots: dict[Key, SnapshotRecord], policy: DatasetPolicy,
    target: Mapping[str, Any],
) -> dict[Key, OutcomeRecord]:
    result: dict[Key, OutcomeRecord] = {}
    for raw in records:
        item = OutcomeRecord.model_validate(raw)
        if item.target_id != policy.target_id:
            continue
        key = (item.query_id, item.candidate_id)
        if key in result or key not in snapshots:
            fail("P7_LTR_QUERY_GROUP_INVALID", f"invalid or duplicate outcome {key}")
        _validate_outcome(item, snapshots[key], policy, target)
        result[key] = item
    return result


def _coverage(
    grouped: dict[str, list[SnapshotRecord]], outcomes: dict[Key, OutcomeRecord], policy: DatasetPolicy
) -> tuple[list[dict[str, Any]], set[str]]:
    records: list[dict[str, Any]] = []
    eligible: set[str] = set()
    for query_id in sorted(grouped):
        rows = grouped[query_id]
        labeled = [row for row in rows if (query_id, row.candidate_id) in outcomes]
        nonselected = [row for row in rows if not row.selected_by_p8]
        labeled_nonselected = [row for row in nonselected if (query_id, row.candidate_id) in outcomes]
        ratio = len(labeled) / len(rows)
        selected_only = bool(nonselected) and not labeled_nonselected
        status = "ELIGIBLE"
        if len(rows) < policy.minimum_candidates_per_query or ratio < policy.min_query_coverage:
            status = "INCOMPLETE"
        if policy.require_nonselected_counterfactuals and selected_only:
            status = "SELECTED_ONLY"
        records.append({
            "query_id": query_id, "candidate_count": len(rows), "labeled_count": len(labeled),
            "nonselected_count": len(nonselected), "labeled_nonselected_count": len(labeled_nonselected),
            "coverage": ratio, "selected_only": selected_only, "status": status,
        })
        if status == "ELIGIBLE":
            eligible.add(query_id)
    return records, eligible


def _training_row(
    snapshot: SnapshotRecord, outcome: OutcomeRecord, target: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "candidate_id": snapshot.candidate_id, "query_id": snapshot.query_id, "cycle_id": snapshot.cycle_id,
        "decision_time": iso_utc(snapshot.decision_time), "label_end_time": iso_utc(outcome.label_end_time),
        "outcome_available_at": iso_utc(outcome.outcome_available_at), "underlying_id": snapshot.underlying_id,
        "horizon": snapshot.horizon, "objective_family": snapshot.objective_family,
        "capital_at_risk_bucket": snapshot.capital_at_risk_bucket,
        "feature_schema_version": snapshot.feature_schema_version,
        "feature_values": dict(sorted(snapshot.features.items())),
        "interpretable_score": snapshot.interpretable_score,
        "utility_label": float(outcome.outcome_value) * float(target["utility_multiplier"]),
        "selected_by_p8": snapshot.selected_by_p8, "candidate_topology": snapshot.candidate_topology,
        "regime": snapshot.regime, "target_id": target["target_id"],
        "target_policy_version": target["policy_version"], "lineage_id": snapshot.lineage_id,
    }


def _apply_regret(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["query_id"]].append(row)
    for query_rows in grouped.values():
        best = max(float(row["utility_label"]) for row in query_rows)
        for row in query_rows:
            row["utility_label"] = float(row["utility_label"]) - best


def _query_records(rows: list[dict[str, Any]], eligible: set[str], schema_hash: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for query_id in sorted(eligible):
        group = [row for row in rows if row["query_id"] == query_id]
        first = group[0]
        result.append({
            "query_id": query_id, "cycle_id": first["cycle_id"], "decision_time": first["decision_time"],
            "underlying_id": first["underlying_id"], "horizon": first["horizon"],
            "objective_family": first["objective_family"],
            "capital_at_risk_bucket": first["capital_at_risk_bucket"], "candidate_count": len(group),
            "label_end_time": max(row["label_end_time"] for row in group),
            "outcome_available_at": max(row["outcome_available_at"] for row in group),
            "feature_schema_hash": schema_hash,
        })
    return result


def build_training_dataset(
    snapshot_records: tuple[dict[str, Any], ...], outcome_records: tuple[dict[str, Any], ...],
    target_policy_records: tuple[dict[str, Any], ...], policy: DatasetPolicy, *, current_cycle_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    target = _policy_record(target_policy_records, policy.target_id)
    snapshots = _parse_snapshots(snapshot_records, policy, current_cycle_id)
    outcomes = _parse_outcomes(outcome_records, snapshots, policy, target)
    grouped: dict[str, list[SnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots.values():
        grouped[snapshot.query_id].append(snapshot)
    coverage, eligible = _coverage(grouped, outcomes, policy)
    overall = len(outcomes) / len(snapshots) if snapshots else 0.0
    if any(row["status"] == "SELECTED_ONLY" for row in coverage):
        fail("P7_LTR_SELECTED_ONLY_LABELS", "selected-only labels are forbidden")
    if overall < policy.min_overall_coverage or not eligible:
        fail("P7_LTR_COUNTERFACTUAL_COVERAGE_INSUFFICIENT", "counterfactual coverage is insufficient")
    rows = [_training_row(snapshot, outcomes[(query_id, snapshot.candidate_id)], target)
            for query_id in sorted(eligible) for snapshot in sorted(grouped[query_id], key=lambda item: item.candidate_id)]
    if target["transformation"] == Transformation.REGRET_TO_BEST.value:
        _apply_regret(rows)
    names = sorted({name for row in rows for name in row["feature_values"]})
    schema_hash = feature_schema_hash(names)
    for row in rows:
        row["feature_schema_hash"] = schema_hash
    coverage.append({
        "query_id": "__OVERALL__", "candidate_count": len(snapshots), "labeled_count": len(outcomes),
        "nonselected_count": sum(not row.selected_by_p8 for row in snapshots.values()),
        "labeled_nonselected_count": sum(not snapshots[key].selected_by_p8 for key in outcomes),
        "coverage": overall, "selected_only": False, "status": "ELIGIBLE",
    })
    return rows, _query_records(rows, eligible, schema_hash), coverage
