from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...domain.canonical import parse_utc
from ...domain.errors import fail


class SplitPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    min_train_sessions: int = Field(ge=2)
    validation_sessions: int = Field(ge=1)
    calibration_sessions: int = Field(ge=1)
    sealed_test_sessions: int = Field(ge=1)
    step_sessions: int = Field(ge=1)
    purge_sessions: int = Field(ge=0)
    embargo_sessions: int = Field(ge=0)
    max_folds: int = Field(ge=1)


def _calendar(records: tuple[dict[str, Any], ...]) -> tuple[list[date], dict[date, int]]:
    if len(records) != 1 or not isinstance(records[0].get("sessions"), list):
        fail("P7_LTR_CALENDAR_INVALID", "exactly one calendar with sessions is required")
    sessions = [date.fromisoformat(str(value)) for value in records[0]["sessions"]]
    if not sessions or sessions != sorted(set(sessions)):
        fail("P7_LTR_CALENDAR_INVALID", "calendar sessions must be unique and sorted")
    return sessions, {session: index for index, session in enumerate(sessions)}


def _query_info(
    records: tuple[dict[str, Any], ...], session_index: dict[date, int]
) -> dict[str, tuple[int, int, datetime]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row["query_id"])].append(dict(row))
    result: dict[str, tuple[int, int, datetime]] = {}
    for query_id, rows in grouped.items():
        decisions = {str(row["decision_time"]) for row in rows}
        if len(decisions) != 1:
            fail("P7_LTR_QUERY_GROUP_INVALID", f"query {query_id} has multiple decision times")
        decision = parse_utc(next(iter(decisions)), field="decision_time")
        label_end = max(parse_utc(str(row["label_end_time"]), field="label_end_time") for row in rows)
        if decision.date() not in session_index or label_end.date() not in session_index:
            fail("P7_LTR_CALENDAR_INVALID", f"query {query_id} date missing from calendar")
        result[query_id] = (session_index[decision.date()], session_index[label_end.date()], decision)
    return result


def _queries_at(info: dict[str, tuple[int, int, datetime]], positions: list[int]) -> list[str]:
    return sorted(query_id for query_id, values in info.items() if values[0] in positions)


def _train_queries(
    info: dict[str, tuple[int, int, datetime]], train_positions: list[int], validation_start: int,
    policy: SplitPolicy,
) -> tuple[list[str], list[str], list[str]]:
    train: list[str] = []
    purged: list[str] = []
    embargoed: list[str] = []
    for query_id, (decision_index, label_end_index, _) in info.items():
        if decision_index not in train_positions:
            continue
        if policy.embargo_sessions and decision_index >= validation_start - policy.embargo_sessions:
            embargoed.append(query_id)
        elif label_end_index >= validation_start - policy.purge_sessions:
            purged.append(query_id)
        else:
            train.append(query_id)
    return sorted(train), sorted(purged), sorted(embargoed)


def _assert_disjoint(groups: list[list[str]]) -> None:
    sets = [set(group) for group in groups]
    for index, left in enumerate(sets):
        for right in sets[index + 1:]:
            if left & right:
                fail("P7_LTR_TEMPORAL_SPLIT_OVERLAP", "query appears in multiple splits")


def _fold(
    number: int, sessions: list[date], info: dict[str, tuple[int, int, datetime]], train_positions: list[int],
    validation_positions: list[int], calibration_positions: list[int], test_positions: list[int], policy: SplitPolicy,
) -> dict[str, Any] | None:
    train, purged, embargoed = _train_queries(info, train_positions, validation_positions[0], policy)
    validation = _queries_at(info, validation_positions)
    calibration = _queries_at(info, calibration_positions)
    test = _queries_at(info, test_positions)
    _assert_disjoint([train, validation, calibration, test])
    if not train or not validation or not calibration:
        return None
    return {
        "fold_id": f"fold-{number:03d}", "train_query_ids": train,
        "validation_query_ids": validation, "calibration_query_ids": calibration,
        "sealed_test_query_ids": test, "purged_query_ids": purged, "embargoed_query_ids": embargoed,
        "train_start_session": sessions[min(train_positions)].isoformat(),
        "train_end_session": sessions[max(train_positions)].isoformat(),
        "validation_start_session": sessions[min(validation_positions)].isoformat(),
        "validation_end_session": sessions[max(validation_positions)].isoformat(),
        "calibration_start_session": sessions[min(calibration_positions)].isoformat(),
        "calibration_end_session": sessions[max(calibration_positions)].isoformat(),
        "test_start_session": sessions[min(test_positions)].isoformat(), "test_sealed": True,
    }


def build_temporal_folds(
    dataset_records: tuple[dict[str, Any], ...], calendar_records: tuple[dict[str, Any], ...], policy: SplitPolicy,
) -> list[dict[str, Any]]:
    sessions, session_index = _calendar(calendar_records)
    info = _query_info(dataset_records, session_index)
    used = sorted({values[0] for values in info.values()})
    required = policy.min_train_sessions + policy.validation_sessions + policy.calibration_sessions + policy.sealed_test_sessions
    if len(used) < required:
        fail("P7_LTR_INSUFFICIENT_QUERIES", "not enough query sessions for split policy")
    test_positions = used[-policy.sealed_test_sessions:]
    pretest = used[:-policy.sealed_test_sessions]
    folds: list[dict[str, Any]] = []
    train_count = policy.min_train_sessions
    for number in range(1, policy.max_folds + 1):
        validation = pretest[train_count:train_count + policy.validation_sessions]
        calibration = pretest[train_count + policy.validation_sessions:train_count + policy.validation_sessions + policy.calibration_sessions]
        if len(validation) < policy.validation_sessions or len(calibration) < policy.calibration_sessions:
            break
        candidate = _fold(number, sessions, info, pretest[:train_count], validation, calibration, test_positions, policy)
        if candidate is not None:
            folds.append(candidate)
        train_count += policy.step_sessions
    if not folds:
        fail("P7_LTR_INSUFFICIENT_QUERIES", "split policy produced no valid folds")
    return folds
