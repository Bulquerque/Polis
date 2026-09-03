"""Semantic validation for final-integration evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from math import isclose

from .hashing import sha256_value
from .models import (
    ActivationTrustSensitivityReport,
    CommitmentCoverageReport,
    CommitmentRecord,
    EvaluationDatasetManifest,
    EvaluationObservationPanel,
    EvaluationSplitManifest,
    ExperimentRegistry,
    OutcomeRecord,
    PopulationCalibrationBundle,
    RuntimeCostLatencyPanel,
    SocialGraphCalibrationReport,
    VariantExecutionManifest,
)

REQUIRED_VARIANTS = (
    "SEARCH_RAG",
    "SINGLE_AGENT",
    "SOCIETY_NO_RELATIONS",
    "SOCIETY_NO_MEMORY",
    "SOCIETY_NO_TOOLS",
    "FULL_SOCIETY",
)


def validate_dataset(manifest: EvaluationDatasetManifest) -> list[str]:
    errors: list[str] = []
    if not manifest.point_in_time_complete:
        errors.append("dataset is not point-in-time complete")
    if not manifest.final_holdout_blinded:
        errors.append("final holdout is not blinded")
    artifact_ids = [item.artifact_id for item in manifest.artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        errors.append("dataset artifact_id values must be unique")
    for item in manifest.artifacts:
        if not all(
            (
                item.corporate_actions_controlled,
                item.delistings_controlled,
                item.survivorship_controlled,
                item.revisions_controlled,
            )
        ):
            errors.append(f"dataset controls incomplete for {item.artifact_id}")
        if item.missingness_rate > 0.25:
            errors.append(f"missingness exceeds hard cap for {item.artifact_id}")
        if item.event_time_max > item.available_at_max:
            # Availability can lag event time, never lead its latest event.
            errors.append(f"availability predates event horizon for {item.artifact_id}")
    return errors


def validate_splits(
    dataset: EvaluationDatasetManifest,
    splits: EvaluationSplitManifest,
    registry: ExperimentRegistry,
) -> list[str]:
    errors: list[str] = []
    if splits.dataset_hash != dataset.dataset_hash:
        errors.append("split dataset_hash mismatch")
    if registry.dataset_hash != dataset.dataset_hash:
        errors.append("experiment dataset_hash mismatch")
    if registry.split_hash != splits.split_hash:
        errors.append("experiment split_hash mismatch")
    if splits.holdout_opened_at is None:
        errors.append("final holdout has not been opened under the frozen protocol")
    elif splits.holdout_opened_at < registry.frozen_at:
        errors.append("holdout was opened before experiment freeze")
    if len(set(registry.seeds)) < 3:
        errors.append("at least three distinct seeds are required")
    if len(splits.splits) < 5:
        errors.append("at least five folds are required")
    return errors


def build_commitment_coverage(
    commitments: Iterable[CommitmentRecord],
    outcomes: Iterable[OutcomeRecord],
    *,
    release_id: str,
    release_sha256: str,
    experiment_id: str,
) -> CommitmentCoverageReport:
    commitments = tuple(commitments)
    outcomes = tuple(outcomes)
    counts = Counter(item.commitment_id for item in commitments)
    duplicate = tuple(sorted(key for key, count in counts.items() if count > 1))
    outcome_map: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for item in outcomes:
        outcome_map[item.commitment_id].append(item)
    unmatched: list[str] = []
    premature: list[str] = []
    matched = 0
    for commitment in commitments:
        candidates = outcome_map.get(commitment.commitment_id, [])
        exact = [
            item
            for item in candidates
            if (
                item.proposition_id,
                item.underlying_id,
                item.horizon,
                item.source_cycle_id,
            )
            == (
                commitment.proposition_id,
                commitment.underlying_id,
                commitment.horizon,
                commitment.source_cycle_id,
            )
        ]
        if len(exact) != 1:
            unmatched.append(commitment.commitment_id)
            continue
        outcome = exact[0]
        if (
            outcome.outcome_available_at < commitment.outcome_available_at
            or outcome.observed_at < commitment.outcome_available_at
        ):
            premature.append(commitment.commitment_id)
            continue
        matched += 1
    ratio = matched / len(commitments) if commitments else 0.0
    status = (
        "PASS"
        if commitments and ratio == 1.0 and not duplicate and not premature
        else "FAIL"
    )
    payload = {
        "report_version": "p3.commitment-coverage.v2",
        "release_id": release_id,
        "release_sha256": release_sha256,
        "experiment_id": experiment_id,
        "commitments": commitments,
        "outcomes": outcomes,
        "matched_count": matched,
        "unmatched_commitment_ids": tuple(sorted(set(unmatched))),
        "duplicate_ids": duplicate,
        "premature_outcome_ids": tuple(sorted(set(premature))),
        "coverage_ratio": ratio,
        "status": status,
        "report_hash": "",
    }
    payload["report_hash"] = sha256_value(payload)
    return CommitmentCoverageReport.model_validate(payload)


def validate_calibration(
    population: PopulationCalibrationBundle,
    graph: SocialGraphCalibrationReport,
    activation: ActivationTrustSensitivityReport,
    registry: ExperimentRegistry,
) -> list[str]:
    errors: list[str] = []
    for item in (population, graph, activation):
        if item.experiment_id != registry.experiment_id:
            errors.append(f"calibration experiment mismatch: {type(item).__name__}")
        if item.release_id != registry.release_id or item.release_sha256 != registry.release_sha256:
            errors.append(f"calibration release mismatch: {type(item).__name__}")
    if population.frozen_at > registry.frozen_at:
        errors.append("population calibration was frozen after the experiment")
    if population.version_stability_score < 0.90:
        errors.append("population version stability below 0.90")
    if population.seed_stability_score < 0.90:
        errors.append("population seed stability below 0.90")
    if set(population.seeds) != set(registry.seeds):
        errors.append("population seeds differ from experiment seeds")
    if population.effective_sample_size < 30:
        errors.append("population effective sample size below 30")
    if not population.resolved_parameters:
        errors.append("population parameters were not resolved")
    expected_graph = {
        "degree_distribution",
        "clustering",
        "assortativity",
        "homophily",
        "centralization",
        "component_sizes",
        "path_length",
    }
    actual_graph = [item.metric for item in graph.comparisons]
    if set(actual_graph) != expected_graph or len(actual_graph) != len(expected_graph):
        errors.append("social graph metrics must be exact and unique")
    if graph.status != "PASS" or any(not item.passed for item in graph.comparisons):
        errors.append("social graph calibration failed")
    expected_stress = {
        "STARVATION",
        "RUNAWAY_FEEDBACK",
        "ARTIFICIAL_POLARIZATION",
        "FROZEN_RELATIONSHIPS",
        "VOLATILE_RELATIONSHIPS",
    }
    actual_stress = [item.scenario for item in activation.scenarios]
    if set(actual_stress) != expected_stress or len(actual_stress) != len(expected_stress):
        errors.append("activation/trust scenarios must be exact and unique")
    if activation.status != "PASS" or any(not item.passed for item in activation.scenarios):
        errors.append("activation/trust stress test failed")
    return errors


def validate_variant_alignment(
    manifest: VariantExecutionManifest,
    observations: EvaluationObservationPanel,
    costs: RuntimeCostLatencyPanel,
    registry: ExperimentRegistry,
    splits: EvaluationSplitManifest,
) -> list[str]:
    errors: list[str] = []
    for item in (manifest, observations, costs):
        if item.experiment_id != registry.experiment_id:
            errors.append(f"experiment mismatch: {type(item).__name__}")
        if item.experiment_registry_hash != registry.registry_hash:
            errors.append(f"experiment registry hash mismatch: {type(item).__name__}")
        if item.release_id != registry.release_id or item.release_sha256 != registry.release_sha256:
            errors.append(f"release mismatch: {type(item).__name__}")

    expected_variants = set(REQUIRED_VARIANTS)
    expected_units = {
        (split.fold_id, seed)
        for split in splits.splits
        for seed in registry.seeds
    }
    split_by_id = {item.fold_id: item for item in splits.splits}
    execution_by_key = {}
    grouped: dict[tuple[str, int], list] = defaultdict(list)
    for row in manifest.records:
        key = (row.unit.fold_id, row.unit.seed, row.variant)
        if key in execution_by_key:
            errors.append(f"duplicate execution record: {key}")
        execution_by_key[key] = row
        grouped[(row.unit.fold_id, row.unit.seed)].append(row)
        expected = {
            "experiment_registry_hash": registry.registry_hash,
            "dataset_hash": registry.dataset_hash,
            "split_hash": registry.split_hash,
            "provider_fingerprint": registry.provider_fingerprint,
            "model_fingerprint": registry.model_fingerprint,
            "prompt_hash": registry.prompt_hash,
            "configuration_hash": registry.configuration_hash,
        }
        for field, value in expected.items():
            if getattr(row.unit, field) != value:
                errors.append(f"{field} mismatch in {key}")
        raw = row.model_dump(mode="json")
        claimed = raw["record_hash"]
        raw["record_hash"] = ""
        if sha256_value(raw) != claimed:
            errors.append(f"execution record self-hash mismatch: {key}")
        if row.started_at < registry.frozen_at:
            errors.append(f"execution predates experiment freeze: {key}")
        split = split_by_id.get(row.unit.fold_id)
        if split is None:
            errors.append(f"unknown fold_id: {row.unit.fold_id}")
        elif split.is_final_holdout:
            if splits.holdout_opened_at is None or row.started_at < splits.holdout_opened_at:
                errors.append(f"holdout execution predates controlled opening: {key}")

    if set(grouped) != expected_units:
        errors.append("execution units do not match the split/seed Cartesian product")
    for key, rows in grouped.items():
        variants = {row.variant for row in rows}
        if variants != expected_variants or len(rows) != len(expected_variants):
            errors.append(f"unaligned or duplicate variants for {key}: {sorted(variants)}")
        for field in (
            "checkpoint_hash",
            "experiment_registry_hash",
            "dataset_hash",
            "split_hash",
            "provider_fingerprint",
            "model_fingerprint",
            "prompt_hash",
            "configuration_hash",
            "cache_hash",
        ):
            if len({getattr(row.unit, field) for row in rows}) != 1:
                errors.append(f"{field} differs across variants for {key}")

    observations_by_key = {}
    observation_ids: set[str] = set()
    for row in observations.observations:
        key = (row.fold_id, row.seed, row.variant)
        if key in observations_by_key:
            errors.append(f"duplicate observation row: {key}")
        observations_by_key[key] = row
        if row.observation_id in observation_ids:
            errors.append(f"duplicate observation_id: {row.observation_id}")
        observation_ids.add(row.observation_id)
        execution = execution_by_key.get(key)
        if execution is None:
            errors.append(f"observation without execution: {key}")
        else:
            if row.execution_record_hash != execution.record_hash:
                errors.append(f"observation execution hash mismatch: {key}")
            if row.output_artifact_hash != execution.output_artifact_hash:
                errors.append(f"observation output hash mismatch: {key}")
    if set(observations_by_key) != set(execution_by_key):
        errors.append("observations do not match execution records exactly")

    costs_by_key = {}
    for row in costs.rows:
        key = (row.fold_id, row.seed, row.variant)
        if key in costs_by_key:
            errors.append(f"duplicate cost row: {key}")
        costs_by_key[key] = row
        execution = execution_by_key.get(key)
        if execution is None:
            errors.append(f"cost row without execution: {key}")
        elif row.execution_record_hash != execution.record_hash:
            errors.append(f"cost execution hash mismatch: {key}")
        total = row.provider_cost + row.storage_cost + row.tool_cost
        if total > costs.cost_budget_per_execution:
            errors.append(f"cost budget exceeded: {key}")
        if row.latency_ms_p95 > costs.latency_budget_ms_p95:
            errors.append(f"latency budget exceeded: {key}")
        observation = observations_by_key.get(key)
        if observation is not None:
            if not isclose(observation.cost, total, rel_tol=1e-9, abs_tol=1e-9):
                errors.append(f"observation/cost panel mismatch: {key}")
            if observation.latency_ms > row.latency_ms_p95:
                errors.append(f"observation latency exceeds recorded p95: {key}")
    if set(costs_by_key) != set(execution_by_key):
        errors.append("cost rows do not match execution records exactly")
    return errors
