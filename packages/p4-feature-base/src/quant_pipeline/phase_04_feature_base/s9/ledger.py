from __future__ import annotations

from collections import defaultdict
from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .errors import S9Error
from .records import ResearchBudgetPolicy

NEGATIVE_STATUSES = {"FAILED", "REJECTED", "ABANDONED", "DUPLICATE", "BLOCKED_CONTRACT"}
TERMINAL_STATUSES = NEGATIVE_STATUSES | {"COMPLETED"}


def _event_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "event_hash"}


def _validate_chain(records: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda item: (str(item["event_time"]), str(item["event_id"])))
    previous: str | None = None
    seen_events: set[str] = set()
    for record in ordered:
        event_id = str(record["event_id"])
        if event_id in seen_events:
            raise S9Error("P4_S9_LEDGER_DUPLICATE_EVENT", event_id)
        seen_events.add(event_id)
        expected_hash = canonical_sha256(_event_payload(record))
        if record.get("event_hash") != expected_hash:
            raise S9Error("P4_S9_LEDGER_HASH_MISMATCH", event_id)
        if record.get("previous_event_hash") != previous:
            raise S9Error("P4_S9_LEDGER_CHAIN_BROKEN", event_id)
        previous = expected_hash
    return ordered


def _compact_attempts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[str(event["attempt_id"])].append(event)
    compacted: list[dict[str, Any]] = []
    for attempt_id, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (str(item["event_time"]), str(item["event_id"])))
        final = ordered[-1]
        compacted.append(
            {
                "attempt_id": attempt_id,
                "hypothesis_id": final.get("hypothesis_id"),
                "observer_id": final.get("observer_id"),
                "parameterization_id": final.get("parameterization_id"),
                "config_id": final.get("config_id"),
                "fold_id": final.get("fold_id"),
                "seed": final.get("seed"),
                "status": final.get("status"),
                "reason_code": final.get("reason_code"),
                "agent_id": final.get("agent_id"),
                "parent_attempt_id": final.get("parent_attempt_id"),
                "first_event_time": ordered[0]["event_time"],
                "last_event_time": final["event_time"],
                "event_count": len(ordered),
                "terminal": final.get("status") in TERMINAL_STATUSES,
                "last_event_hash": final["event_hash"],
            }
        )
    return compacted


def _compliance(
    ledger: list[dict[str, Any]], policy: ResearchBudgetPolicy
) -> tuple[list[dict[str, Any]], bool]:
    hypothesis_ids = {str(item["hypothesis_id"]) for item in ledger if item.get("hypothesis_id")}
    parameters: dict[str, set[str]] = defaultdict(set)
    encoder_configs: set[str] = set()
    for item in ledger:
        hypothesis = item.get("hypothesis_id")
        parameter = item.get("parameterization_id")
        if hypothesis and parameter:
            parameters[str(hypothesis)].add(str(parameter))
        if item.get("config_id"):
            encoder_configs.add(str(item["config_id"]))
    max_parameters = max((len(values) for values in parameters.values()), default=0)
    negative_count = sum(str(item.get("status")) in NEGATIVE_STATUSES for item in ledger)
    checks = [
        {
            "check_id": "FOUNDATIONAL_HYPOTHESES",
            "observed": len(hypothesis_ids),
            "limit": policy.expected_foundational_hypotheses,
            "operator": "EQUAL",
            "status": "PASS" if len(hypothesis_ids) == policy.expected_foundational_hypotheses else "BLOCK",
        },
        {
            "check_id": "PARAMETERIZATIONS_PER_HYPOTHESIS",
            "observed": max_parameters,
            "limit": policy.max_parameterizations_per_hypothesis,
            "operator": "LESS_OR_EQUAL",
            "status": "PASS" if max_parameters <= policy.max_parameterizations_per_hypothesis else "BLOCK",
        },
        {
            "check_id": "ENCODER_CONFIGURATIONS",
            "observed": len(encoder_configs),
            "limit": policy.max_encoder_configurations,
            "operator": "LESS_OR_EQUAL",
            "status": "PASS" if len(encoder_configs) <= policy.max_encoder_configurations else "BLOCK",
        },
        {
            "check_id": "NEGATIVE_RESULTS_PRESERVED",
            "observed": negative_count,
            "limit": 1 if policy.require_negative_results else 0,
            "operator": "GREATER_OR_EQUAL",
            "status": "PASS" if (negative_count > 0 or not policy.require_negative_results) else "BLOCK",
        },
    ]
    return checks, all(item["status"] == "PASS" for item in checks)


def build_ledger_outputs(
    event_log: ArtifactEnvelope,
    policy: ResearchBudgetPolicy,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    events = _validate_chain(event_log.records)
    ledger = _compact_attempts(events)
    graveyard = [item for item in ledger if str(item["status"]) in NEGATIVE_STATUSES]
    compliance, passed = _compliance(ledger, policy)
    lineage = canonical_sha256(
        {"event_log": event_log.artifact_id, "last_hash": events[-1]["event_hash"] if events else None}
    )
    return {
        "research_attempt_ledger": build_artifact(
            artifact_name="research_attempt_ledger",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M06",
            context=context,
            grain=("attempt_id",),
            records=ledger,
            lineage_id=lineage,
            metadata={"append_only_chain_validated": True, "source_event_count": len(events)},
        ),
        "rejected_feature_graveyard": build_artifact(
            artifact_name="rejected_feature_graveyard",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M06",
            context=context,
            grain=("attempt_id",),
            records=graveyard,
            lineage_id=lineage,
            metadata={"negative_results_preserved": True},
        ),
        "research_budget_compliance_report": build_artifact(
            artifact_name="research_budget_compliance_report",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M06",
            context=context,
            grain=("check_id",),
            records=compliance,
            lineage_id=lineage,
            metadata={"compliance_passed": passed},
            execution_status="PRODUCED" if passed else "BLOCKED",
            quality_status="VALIDATED" if passed else "BLOCKED",
        ),
    }
