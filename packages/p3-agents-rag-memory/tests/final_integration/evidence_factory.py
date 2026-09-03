from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.final_integration.hashing import (
    public_key_base64,
    sha256_file,
    sha256_value,
    sign_mapping_ed25519,
)
from quant_pipeline.phase_03_agents_rag_memory.final_integration.models import (
    Authority,
    P0PromotionDecision,
    PublicKeyRecord,
    ReceiptType,
    SignedReceipt,
    VariantExecutionRecord,
)
from quant_pipeline.phase_03_agents_rag_memory.final_integration.receipts import (
    EXPECTED_ARTIFACTS,
)

RELEASE_ID = "P3-FINAL-INTEGRATION"
RELEASE_SHA256 = sha256_value("final-release-archive")
EXPERIMENT_ID = "exp-final"
COUNTS = {
    1: 2, 2: 3, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2, 9: 1,
    10: 2, 11: 3, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2, 17: 2,
    18: 2, 19: 2, 20: 7, 21: 6, 22: 3, 23: 2, 24: 3, 25: 3,
    26: 3, 27: 3, 28: 3, 29: 2, 30: 5, 31: 2,
}
MODULES = [
    f"P3.S{subphase}.M{module:02d}"
    for subphase, count in COUNTS.items()
    for module in range(1, count + 1)
]
VARIANTS = [
    "SEARCH_RAG",
    "SINGLE_AGENT",
    "SOCIETY_NO_RELATIONS",
    "SOCIETY_NO_MEMORY",
    "SOCIETY_NO_TOOLS",
    "FULL_SOCIETY",
]


def _private_key(label: str) -> str:
    raw = hashlib.sha256(f"test-key::{label}".encode()).digest()
    return base64.b64encode(raw).decode("ascii")


PRIVATE_KEYS = {
    Authority.OPERATIONS: _private_key("operations"),
    Authority.P2: _private_key("p2"),
    Authority.P3_RUNTIME: _private_key("p3-runtime"),
    Authority.P4: _private_key("p4"),
    Authority.P9: _private_key("p9"),
    Authority.P0: _private_key("p0"),
}
KEY_IDS = {authority: f"{authority.value.lower()}-key" for authority in Authority}
KEYRING = {
    KEY_IDS[authority]: PublicKeyRecord(
        authority=authority,
        public_key=public_key_base64(private_key),
        enabled=True,
    )
    for authority, private_key in PRIVATE_KEYS.items()
}


def write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def seal(payload: dict, field: str) -> dict:
    payload[field] = ""
    payload[field] = sha256_value(payload)
    return payload


def signed_receipt(
    receipt_type: ReceiptType,
    *,
    source: str = "cycle-N",
    target: str | None = None,
) -> dict:
    from quant_pipeline.phase_03_agents_rag_memory.final_integration.receipts import (
        EXPECTED_AUTHORITIES,
    )

    authority = EXPECTED_AUTHORITIES[receipt_type]
    artifact_ids = sorted(EXPECTED_ARTIFACTS[receipt_type])
    downstream = receipt_type in {
        ReceiptType.P4_CONSUMPTION,
        ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION,
    }
    payload = {
        "receipt_version": "p3.integration.receipt.v2",
        "receipt_type": receipt_type,
        "authority": authority,
        "producer": authority.value,
        "consumer": "P3" if authority is not Authority.P4 else "P4",
        "release_id": RELEASE_ID,
        "release_sha256": RELEASE_SHA256,
        "artifact_ids": artifact_ids,
        "artifact_hashes": {item: sha256_value(item) for item in artifact_ids},
        "schema_versions": {item: "1.0.0" for item in artifact_ids},
        "cardinalities": {item: 1 for item in artifact_ids},
        "grains": {item: "canonical" for item in artifact_ids},
        "validation_status": "PASS",
        "source_cycle_id": source,
        "target_cycle_id": target,
        "consumed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "downstream_output_id": "downstream-output" if downstream else None,
        "downstream_output_hash": sha256_value("downstream-output") if downstream else None,
        "key_id": KEY_IDS[authority],
        "signature": "A" * 88,
    }
    provisional = SignedReceipt.model_validate(payload)
    normalized = provisional.model_dump(mode="json")
    normalized["signature"] = sign_mapping_ed25519(
        provisional.unsigned_payload(), PRIVATE_KEYS[authority]
    )
    return SignedReceipt.model_validate(normalized).model_dump(mode="json")


def _release_fields() -> dict[str, str]:
    return {"release_id": RELEASE_ID, "release_sha256": RELEASE_SHA256}


def build_valid_evidence(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    entry = seal(
        {
            "evidence_version": "p3.integration-entry.v2",
            **_release_fields(),
            "code_and_migration_status": "PASS",
            "runtime_qualification_status": "PASS",
            "real_trace_module_ids": MODULES,
            "receipts": [
                signed_receipt(ReceiptType.PLATFORM_QUALIFICATION),
                signed_receipt(ReceiptType.P2_HANDOFF),
                signed_receipt(ReceiptType.CHECKPOINT_RELOAD),
                signed_receipt(ReceiptType.MODULE_TRACE),
            ],
            "holdout_policy_hash": sha256_value("holdout-policy"),
            "frozen_at": "2026-01-01T00:00:00+00:00",
        },
        "evidence_hash",
    )
    write(root / "integration_entry_evidence.json", entry)

    artifact = {
        "artifact_id": "market-data",
        "source_id": "source",
        "source_hash": sha256_value("source"),
        "schema_version": "1.0.0",
        "event_time_min": "2020-01-01T00:00:00+00:00",
        "event_time_max": "2025-01-01T00:00:00+00:00",
        "available_at_min": "2020-01-01T01:00:00+00:00",
        "available_at_max": "2025-01-01T01:00:00+00:00",
        "ingested_at_max": "2025-01-01T02:00:00+00:00",
        "underlying_ids": ["ABC"],
        "corporate_actions_controlled": True,
        "delistings_controlled": True,
        "survivorship_controlled": True,
        "revisions_controlled": True,
        "missingness_rate": 0.01,
        "spread_source": "quote",
        "slippage_source": "execution",
        "liquidity_source": "volume",
        "capacity_source": "adv",
    }
    dataset = seal(
        {
            "manifest_version": "p3.evaluation-dataset.v2",
            **_release_fields(),
            "dataset_id": "dataset",
            "artifacts": [artifact],
            "created_at": "2026-01-01T00:00:00+00:00",
            "point_in_time_complete": True,
            "final_holdout_blinded": True,
        },
        "dataset_hash",
    )
    write(root / "evaluation_dataset_manifest.json", dataset)

    splits = []
    base = datetime(2021, 1, 1, tzinfo=UTC)
    for index in range(5):
        train_start = base + timedelta(days=index * 200)
        train_end = train_start + timedelta(days=100)
        test_start = train_end + timedelta(days=2)
        test_end = test_start + timedelta(days=30)
        splits.append(
            {
                "fold_id": f"fold-{index}",
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "purge_seconds": 86400,
                "embargo_seconds": 86400,
                "is_final_holdout": index == 4,
            }
        )
    split_manifest = seal(
        {
            "manifest_version": "p3.evaluation-splits.v2",
            **_release_fields(),
            "dataset_hash": dataset["dataset_hash"],
            "splits": splits,
            "final_holdout_fold_id": "fold-4",
            "holdout_opened_at": "2026-01-02T00:00:00+00:00",
        },
        "split_hash",
    )
    write(root / "evaluation_split_manifest.json", split_manifest)

    registry = seal(
        {
            "registry_version": "p3.experiment-registry.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "dataset_hash": dataset["dataset_hash"],
            "split_hash": split_manifest["split_hash"],
            "variants": VARIANTS,
            "seeds": [1, 2, 3],
            "prompt_hash": sha256_value("prompt"),
            "model_fingerprint": sha256_value("model"),
            "provider_fingerprint": sha256_value("provider"),
            "configuration_hash": sha256_value("config"),
            "cache_policy_hash": sha256_value("cache-policy"),
            "primary_metrics": [
                {
                    "metric": "brier_score",
                    "direction": "LOWER",
                    "minimum_delta": 0.05,
                    "alpha": 0.05,
                    "guardrail": False,
                }
            ],
            "frozen_at": "2026-01-01T00:00:00+00:00",
            "holdout_access_policy": "BLIND_UNTIL_FROZEN",
        },
        "registry_hash",
    )
    write(root / "experiment_registry.json", registry)

    commitments = []
    outcomes = []
    for index in range(15):
        commitments.append(
            {
                "commitment_id": f"c{index}",
                "proposition_id": "p",
                "underlying_id": "ABC",
                "horizon": "1D",
                "source_cycle_id": f"n{index}",
                "as_of_time": "2025-01-01T00:00:00+00:00",
                "created_at": "2024-12-31T23:00:00+00:00",
                "outcome_available_at": "2025-01-02T00:00:00+00:00",
                "commitment_hash": sha256_value(f"c{index}"),
            }
        )
        outcomes.append(
            {
                "commitment_id": f"c{index}",
                "proposition_id": "p",
                "underlying_id": "ABC",
                "horizon": "1D",
                "source_cycle_id": f"n{index}",
                "outcome_available_at": "2025-01-02T00:00:00+00:00",
                "observed_at": "2025-01-02T01:00:00+00:00",
                "outcome_hash": sha256_value(f"o{index}"),
            }
        )
    coverage = seal(
        {
            "report_version": "p3.commitment-coverage.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "commitments": commitments,
            "outcomes": outcomes,
            "matched_count": 15,
            "unmatched_commitment_ids": [],
            "duplicate_ids": [],
            "premature_outcome_ids": [],
            "coverage_ratio": 1.0,
            "status": "PASS",
        },
        "report_hash",
    )
    write(root / "commitment_coverage_report.json", coverage)

    prior = {
        "source_type": "OBSERVED_DATA",
        "source_id": "survey",
        "source_hash": sha256_value("survey"),
        "citation_or_owner": "owner",
        "effective_at": "2025-01-01T00:00:00+00:00",
    }
    population = seal(
        {
            "bundle_version": "p3.population-calibration.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "prior_sources": [prior],
            "resolved_parameters": {"size": 50, "epsilon": 0.1},
            "seeds": [1, 2, 3],
            "version_stability_score": 0.95,
            "seed_stability_score": 0.96,
            "effective_sample_size": 40,
            "sensitivity_curve": [
                {
                    "parameter": "epsilon",
                    "value": value,
                    "coverage": 0.95,
                    "density": 1.0,
                    "effective_sample_size": 40,
                }
                for value in [0.05, 0.1, 0.2]
            ],
            "frozen_at": "2026-01-01T00:00:00+00:00",
        },
        "bundle_hash",
    )
    write(root / "population_calibration_bundle.json", population)

    comparisons = [
        {
            "metric": metric,
            "observed": 1.0,
            "generated": 1.0,
            "tolerance": 0.1,
            "passed": True,
        }
        for metric in [
            "degree_distribution",
            "clustering",
            "assortativity",
            "homophily",
            "centralization",
            "component_sizes",
            "path_length",
        ]
    ]
    graph = seal(
        {
            "report_version": "p3.social-graph-calibration.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "benchmark_source": prior,
            "comparisons": comparisons,
            "status": "PASS",
        },
        "report_hash",
    )
    write(root / "social_graph_calibration_report.json", graph)

    scenarios = [
        {"scenario": scenario, "threshold": 1.0, "observed": 0.1, "passed": True}
        for scenario in [
            "STARVATION",
            "RUNAWAY_FEEDBACK",
            "ARTIFICIAL_POLARIZATION",
            "FROZEN_RELATIONSHIPS",
            "VOLATILE_RELATIONSHIPS",
        ]
    ]
    activation = seal(
        {
            "report_version": "p3.activation-trust-sensitivity.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "scenarios": scenarios,
            "status": "PASS",
        },
        "report_hash",
    )
    write(root / "activation_trust_sensitivity_report.json", activation)

    executions = []
    observations = []
    costs = []
    for fold in range(5):
        for seed in [1, 2, 3]:
            unit = {
                "fold_id": f"fold-{fold}",
                "seed": seed,
                "experiment_registry_hash": registry["registry_hash"],
                "checkpoint_hash": sha256_value(f"checkpoint-{fold}-{seed}"),
                "dataset_hash": dataset["dataset_hash"],
                "split_hash": split_manifest["split_hash"],
                "provider_fingerprint": registry["provider_fingerprint"],
                "model_fingerprint": registry["model_fingerprint"],
                "prompt_hash": registry["prompt_hash"],
                "configuration_hash": registry["configuration_hash"],
                "cache_hash": sha256_value(f"cache-{fold}-{seed}"),
            }
            for variant in VARIANTS:
                ablated = {
                    "SEARCH_RAG": "SEARCH_ONLY",
                    "SINGLE_AGENT": "SOCIETY",
                    "SOCIETY_NO_RELATIONS": "RELATIONS",
                    "SOCIETY_NO_MEMORY": "MEMORY",
                    "SOCIETY_NO_TOOLS": "TOOLS",
                    "FULL_SOCIETY": "NONE",
                }[variant]
                raw_record = {
                    "variant": variant,
                    "unit": unit,
                    "ablated_component": ablated,
                    "execution_trace_hash": sha256_value(
                        f"trace-{fold}-{seed}-{variant}"
                    ),
                    "output_artifact_hash": sha256_value(
                        f"out-{fold}-{seed}-{variant}"
                    ),
                    "source_kind": "REAL_PIPELINE",
                    "started_at": "2026-01-03T00:00:00+00:00",
                    "completed_at": "2026-01-03T00:01:00+00:00",
                    "record_hash": "0" * 64,
                }
                provisional_record = VariantExecutionRecord.model_validate(raw_record)
                record = provisional_record.model_dump(mode="json")
                record["record_hash"] = ""
                record["record_hash"] = sha256_value(record)
                record = VariantExecutionRecord.model_validate(record).model_dump(mode="json")
                executions.append(record)
                brier = 0.10 if variant == "FULL_SOCIETY" else 0.22
                total_cost = 1.2
                observations.append(
                    {
                        "experiment_id": EXPERIMENT_ID,
                        "variant": variant,
                        "fold_id": f"fold-{fold}",
                        "seed": seed,
                        "observation_id": f"{fold}-{seed}-{variant}",
                        "execution_record_hash": record["record_hash"],
                        "output_artifact_hash": record["output_artifact_hash"],
                        "brier_score": brier,
                        "log_loss": brier,
                        "net_return": 0.02 if variant == "FULL_SOCIETY" else 0.01,
                        "volatility": 0.1,
                        "max_drawdown": 0.05,
                        "turnover": 0.2,
                        "cost": total_cost,
                        "latency_ms": 10.0,
                        "evidence_coverage": 0.95,
                        "effective_sample_size": 30,
                        "pit_integrity": True,
                        "authority_integrity": True,
                        "source_kind": "REAL_PIPELINE",
                    }
                )
                costs.append(
                    {
                        "variant": variant,
                        "fold_id": f"fold-{fold}",
                        "seed": seed,
                        "execution_record_hash": record["record_hash"],
                        "provider_cost": 1.0,
                        "storage_cost": 0.1,
                        "tool_cost": 0.1,
                        "latency_ms_p50": 10,
                        "latency_ms_p95": 20,
                    }
                )
    variants = seal(
        {
            "manifest_version": "p3.variant-execution.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "experiment_registry_hash": registry["registry_hash"],
            "records": executions,
        },
        "manifest_hash",
    )
    write(root / "variant_execution_manifest.json", variants)
    observation_panel = seal(
        {
            "panel_version": "p3.evaluation-observations.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "experiment_registry_hash": registry["registry_hash"],
            "observations": observations,
        },
        "panel_hash",
    )
    write(root / "evaluation_observation_panel.json", observation_panel)
    cost_panel = seal(
        {
            "panel_version": "p3.runtime-cost-latency.v2",
            **_release_fields(),
            "experiment_id": EXPERIMENT_ID,
            "experiment_registry_hash": registry["registry_hash"],
            "rows": costs,
            "cost_budget_per_execution": 3.0,
            "latency_budget_ms_p95": 100,
        },
        "panel_hash",
    )
    write(root / "runtime_cost_latency_panel.json", cost_panel)

    receipt_bundle = seal(
        {
            "bundle_version": "p3.cross-phase-receipts.v2",
            **_release_fields(),
            "receipts": [
                signed_receipt(ReceiptType.P4_CONSUMPTION),
                signed_receipt(ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION),
                signed_receipt(ReceiptType.P9_EVALUATION),
                signed_receipt(ReceiptType.P9_FEEDBACK, source="N", target="N+1"),
                signed_receipt(
                    ReceiptType.N_PLUS_1_FEEDBACK, source="N", target="N+1"
                ),
            ],
        },
        "bundle_hash",
    )
    write(root / "cross_phase_receipts.json", receipt_bundle)

    check_ids = [
        "MODULE_REGRESSION",
        "REPOSITORY_REGRESSION",
        "RUFF",
        "MYPY",
        "COVERAGE",
        "LOAD",
        "CONCURRENCY",
        "DISASTER_RECOVERY",
        "PRISTINE_INSTALL",
        "MIGRATION_IDEMPOTENCE",
        "ROLLBACK_PRISTINE",
        "SBOM",
        "DEPENDENCY_LOCK",
        "SILENT_FALLBACK_SCAN",
    ]
    checks = []
    for check_id in check_ids:
        evidence_path = f"qualification/{check_id.lower()}.txt"
        evidence_file = root / evidence_path
        write(evidence_file, {"check_id": check_id, "status": "PASS"})
        checks.append(
            {
                "check_id": check_id,
                "status": "PASS",
                "command": f"verify {check_id.lower()}",
                "evidence_path": evidence_path,
                "evidence_sha256": sha256_file(evidence_file),
                "executed_at": "2026-01-04T00:00:00+00:00",
                "tool_version": "test",
            }
        )
    qualification = seal(
        {
            "summary_version": "p3.qualification-summary.v2",
            **_release_fields(),
            "module_count": 81,
            "coverage_percent": 90.0,
            "silent_fallback_count": 0,
            "checks": checks,
        },
        "evidence_hash",
    )
    write(root / "qualification_summary.json", qualification)


def add_candidate_and_p0(root: Path, engine) -> None:
    candidate = engine.build_candidate(root, engine.evaluate(root))
    write(root / "promotion_candidate_bundle.json", candidate.model_dump(mode="json"))
    payload = {
        "decision_version": "p0.p3-promotion-decision.v2",
        **_release_fields(),
        "candidate_bundle_hash": candidate.bundle_hash,
        "decision": "PROMOTE",
        "decided_at": "2026-02-01T00:00:00+00:00",
        "authority": Authority.P0,
        "key_id": KEY_IDS[Authority.P0],
        "signature": "A" * 88,
    }
    provisional = P0PromotionDecision.model_validate(payload)
    normalized = provisional.model_dump(mode="json")
    normalized["signature"] = sign_mapping_ed25519(
        provisional.unsigned_payload(), PRIVATE_KEYS[Authority.P0]
    )
    model = P0PromotionDecision.model_validate(normalized)
    write(root / "p0_promotion_decision.json", model.model_dump(mode="json"))
