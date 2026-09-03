"""P7.S1.M02 — reconcile candidate identity across P6 artifacts."""

from __future__ import annotations

from copy import deepcopy

from pydantic import JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact
from ..errors import P7S1Error
from ..models import ModuleConfig
from ..reason_codes import ReasonCode
from .common import records_by_key

MODULE_ID = "P7.S1.M02"
PRIMARY = "strategy_candidate_panel"
MARKET = "strategy_market_snapshot"
MANDATORY_MANY = {
    "strategy_leg_panel": "legs",
    "strategy_payoff_panel": "payoffs",
    "strategy_scenario_evaluation_panel": "scenario_evaluations",
    "strategy_generation_trace_panel": "generation_trace",
}
MANDATORY_ONE = {
    "strategy_risk_panel": "risk",
    "strategy_cost_liquidity_panel": "cost_liquidity",
    "strategy_lineage_panel": "lineage",
}
OPTIONAL_MANY = {
    "strategy_ambiguity_evaluation_panel": "ambiguity_evaluations",
    "strategy_greek_panel": "greeks",
    "candidate_equivalence_panel": "equivalence",
    "quality_diversity_archive": "quality_diversity",
}
OPTIONAL_ONE = {
    "candidate_feature_base_panel": "feature_base",
}
CANDIDATE_KEYS = (
    "candidate_id",
    "cycle_id",
    "decision_time",
    "underlying_id",
    "horizon",
    "objective_family",
    "market_snapshot_id",
    "lineage_id",
)


def execute(index_payload: dict[str, JsonValue], config_payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    config, index = _parse_inputs(index_payload, config_payload)
    artifacts = _extract_artifacts(index)
    candidate_groups, child_groups, snapshots = _build_groups(artifacts)
    _reject_duplicate_primaries(candidate_groups)
    _reject_orphans(child_groups, set(candidate_groups))
    bundles, missing = _reconcile_candidates(candidate_groups, child_groups, snapshots)
    if missing:
        _raise_missing(missing)
    return _build_outputs(config, artifacts, bundles)


def _parse_inputs(index_payload, config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        index = ArtifactEnvelope.model_validate(index_payload)
    except ValidationError as exc:
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "verified P6 artifact index is invalid",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    if index.artifact_name != "verified_p6_artifact_index" or index.record_count != 1:
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "M02 requires one verified P6 artifact index record",
            MODULE_ID,
        )
    return config, index


def _extract_artifacts(index):
    raw_artifacts = index.records[0].get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise P7S1Error(
            ReasonCode.P6_MANIFEST_INVALID,
            "verified index does not contain artifacts",
            MODULE_ID,
        )
    artifacts = [ArtifactEnvelope.model_validate(item) for item in raw_artifacts]
    return {item.artifact_name: item for item in artifacts}


def _build_groups(artifacts):
    _require_keyed_records(artifacts[PRIMARY].records, "candidate_id", PRIMARY)
    candidates = records_by_key(artifacts[PRIMARY].records, "candidate_id")
    relevant = (
        set(MANDATORY_MANY)
        | set(MANDATORY_ONE)
        | (set(OPTIONAL_MANY) & set(artifacts))
        | (set(OPTIONAL_ONE) & set(artifacts))
    )
    for name in relevant:
        _require_keyed_records(artifacts[name].records, "candidate_id", name)
    children = {name: records_by_key(artifacts[name].records, "candidate_id") for name in relevant}
    snapshots = records_by_key(artifacts[MARKET].records, "market_snapshot_id")
    return candidates, children, snapshots



def _require_keyed_records(records, key, artifact_name) -> None:
    invalid = [index for index, record in enumerate(records) if not isinstance(record.get(key), str)]
    if invalid:
        reason = ReasonCode.CANDIDATE_ID_MISMATCH if artifact_name == PRIMARY else ReasonCode.ORPHAN_CHILD_RECORD
        raise P7S1Error(
            reason,
            "artifact contains records without a valid relation key",
            MODULE_ID,
            {"artifact_name": artifact_name, "key": key, "record_indexes": invalid[:50]},
        )


def _validate_related_identity(candidate, bundle) -> None:
    expected = {key: candidate.get(key) for key in ("cycle_id", "decision_time", "underlying_id", "horizon")}
    related = []
    for key in ("legs", "payoffs", "scenario_evaluations", "generation_trace"):
        related.extend(bundle[key])
    related.extend([bundle["risk"], bundle["cost_liquidity"], bundle["lineage"]])
    mismatches = []
    for record in related:
        if not isinstance(record, dict):
            continue
        for key, wanted in expected.items():
            actual = record.get(key)
            if actual is not None and actual != wanted:
                mismatches.append({"field": key, "actual": actual, "expected": wanted})
    if mismatches:
        raise P7S1Error(
            ReasonCode.CANDIDATE_ID_MISMATCH,
            "candidate child identity conflicts with its primary record",
            MODULE_ID,
            {"candidate_id": candidate.get("candidate_id"), "mismatches": mismatches[:50]},
        )

def _reject_duplicate_primaries(candidate_groups) -> None:
    duplicates = sorted(key for key, values in candidate_groups.items() if len(values) != 1)
    if duplicates:
        raise P7S1Error(
            ReasonCode.CANDIDATE_PRIMARY_DUPLICATE,
            "candidate primary records are not unique",
            MODULE_ID,
            {"candidate_ids": duplicates},
        )


def _reject_orphans(child_groups, known_candidates) -> None:
    rows = _collect_orphans(child_groups, known_candidates)
    if rows:
        raise P7S1Error(
            ReasonCode.ORPHAN_CHILD_RECORD,
            "child records reference unknown candidates",
            MODULE_ID,
            {"orphan_count": len(rows), "sample": rows[:10]},
        )


def _reconcile_candidates(candidate_groups, child_groups, snapshots):
    bundles: list[dict[str, JsonValue]] = []
    missing: list[dict[str, JsonValue]] = []
    for candidate_id in sorted(candidate_groups):
        bundle, candidate_missing = _reconcile_candidate(
            candidate_id,
            candidate_groups[candidate_id][0],
            child_groups,
            snapshots,
        )
        bundles.append(bundle)
        missing.extend(candidate_missing)
    return bundles, missing


def _reconcile_candidate(candidate_id, candidate, child_groups, snapshots):
    missing_keys = [key for key in CANDIDATE_KEYS if not candidate.get(key)]
    if missing_keys:
        raise P7S1Error(
            ReasonCode.CANDIDATE_ID_MISMATCH,
            "candidate primary record is missing identity fields",
            MODULE_ID,
            {"candidate_id": candidate_id, "missing_keys": missing_keys},
        )
    bundle = {key: deepcopy(candidate[key]) for key in CANDIDATE_KEYS}
    bundle["candidate"] = deepcopy(candidate)
    missing: list[dict[str, JsonValue]] = []
    _attach_mandatory_many(bundle, candidate_id, child_groups, missing)
    _attach_mandatory_one(bundle, candidate_id, child_groups, missing)
    _attach_snapshot(bundle, candidate, candidate_id, snapshots, missing)
    for artifact_name, output_name in OPTIONAL_MANY.items():
        bundle[output_name] = child_groups.get(artifact_name, {}).get(candidate_id, [])
    for artifact_name, output_name in OPTIONAL_ONE.items():
        rows = child_groups.get(artifact_name, {}).get(candidate_id, [])
        bundle[output_name] = rows[0] if len(rows) == 1 else {}
    _validate_related_identity(candidate, bundle)
    _validate_capabilities(candidate, bundle)
    return bundle, missing


def _attach_mandatory_many(bundle, candidate_id, child_groups, missing) -> None:
    for artifact_name, output_name in MANDATORY_MANY.items():
        rows = child_groups[artifact_name].get(candidate_id, [])
        if not rows:
            missing.append({"candidate_id": candidate_id, "artifact_name": artifact_name})
        bundle[output_name] = rows


def _attach_mandatory_one(bundle, candidate_id, child_groups, missing) -> None:
    for artifact_name, output_name in MANDATORY_ONE.items():
        rows = child_groups[artifact_name].get(candidate_id, [])
        if len(rows) != 1:
            missing.append({"candidate_id": candidate_id, "artifact_name": artifact_name, "count": len(rows)})
        bundle[output_name] = rows[0] if len(rows) == 1 else None


def _attach_snapshot(bundle, candidate, candidate_id, snapshots, missing) -> None:
    rows = snapshots.get(str(candidate["market_snapshot_id"]), [])
    if len(rows) != 1:
        missing.append({"candidate_id": candidate_id, "artifact_name": MARKET, "count": len(rows)})
    bundle["market_snapshot"] = rows[0] if len(rows) == 1 else None


def _raise_missing(missing) -> None:
    raise P7S1Error(
        ReasonCode.CANDIDATE_MANDATORY_RECORD_MISSING,
        "one or more candidates cannot be reconstructed from mandatory P6 records",
        MODULE_ID,
        {"missing": missing[:50], "missing_count": len(missing)},
    )


def _build_outputs(config, artifacts, bundles):
    report_record = {
        "status": "PASS",
        "candidate_count": len(bundles),
        "artifact_count": len(artifacts),
        "mandatory_relation_count": len(MANDATORY_MANY) + len(MANDATORY_ONE) + 1,
        "orphan_count": 0,
    }
    bundle_artifact = create_artifact(
        artifact_name="validated_strategy_candidate_bundle",
        records=bundles,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_candidate",
    )
    report = create_artifact(
        artifact_name="candidate_reconciliation_report",
        records=[report_record],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_reconciliation_run",
    )
    orphan_report = create_artifact(
        artifact_name="orphan_record_report",
        records=[],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_orphan_child",
    )
    return {
        "validated_strategy_candidate_bundle": bundle_artifact.model_dump(mode="json"),
        "candidate_reconciliation_report": report.model_dump(mode="json"),
        "orphan_record_report": orphan_report.model_dump(mode="json"),
    }


def _collect_orphans(child_groups, known_candidates):
    rows = []
    for artifact_name, groups in child_groups.items():
        for candidate_id in sorted(set(groups) - known_candidates):
            rows.append(
                {
                    "artifact_name": artifact_name,
                    "candidate_id": candidate_id,
                    "record_count": len(groups[candidate_id]),
                }
            )
    return rows


def _validate_capabilities(candidate, bundle) -> None:
    capabilities = candidate.get("capabilities", {})
    if not isinstance(capabilities, dict):
        return
    mapping = {
        "ambiguity": "ambiguity_evaluations",
        "greeks": "greeks",
        "equivalence": "equivalence",
        "quality_diversity": "quality_diversity",
    }
    conflicts = []
    for capability, bundle_key in mapping.items():
        status = capabilities.get(capability)
        present = bool(bundle[bundle_key])
        if (status == "AVAILABLE" and not present) or (status == "UNAVAILABLE" and present):
            conflicts.append({"capability": capability, "status": status, "present": present})
    if conflicts:
        raise P7S1Error(
            ReasonCode.CAPABILITY_STATUS_INCONSISTENT,
            "candidate capability status conflicts with supplied records",
            MODULE_ID,
            {"candidate_id": candidate.get("candidate_id"), "conflicts": conflicts},
        )
