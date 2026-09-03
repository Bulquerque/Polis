"""Sequential, fail-closed gates for final P3 integration and promotion."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .hashing import (
    sha256_file,
    sha256_value,
    valid_sha256,
    verify_mapping_ed25519,
)
from .models import (
    ActivationTrustSensitivityReport,
    Authority,
    CommitmentCoverageReport,
    CrossPhaseReceiptBundle,
    EvaluationDatasetManifest,
    EvaluationObservationPanel,
    EvaluationSplitManifest,
    ExperimentRegistry,
    GateResult,
    GateStatus,
    IntegrationEntryEvidence,
    IntegrationGateReport,
    P0PromotionDecision,
    PopulationCalibrationBundle,
    PromotionCandidateBundle,
    PublicKeyRecord,
    QualificationSummary,
    ReceiptType,
    RuntimeCostLatencyPanel,
    SocialGraphCalibrationReport,
    VariantExecutionManifest,
)
from .receipts import verify_required_receipts
from .statistics import evaluate_real_observations
from .validation import (
    validate_calibration,
    validate_dataset,
    validate_splits,
    validate_variant_alignment,
)

FILES = {
    "entry": "integration_entry_evidence.json",
    "dataset": "evaluation_dataset_manifest.json",
    "splits": "evaluation_split_manifest.json",
    "experiment": "experiment_registry.json",
    "commitments": "commitment_coverage_report.json",
    "population": "population_calibration_bundle.json",
    "graph": "social_graph_calibration_report.json",
    "activation": "activation_trust_sensitivity_report.json",
    "variants": "variant_execution_manifest.json",
    "observations": "evaluation_observation_panel.json",
    "costs": "runtime_cost_latency_panel.json",
    "receipts": "cross_phase_receipts.json",
    "qualification": "qualification_summary.json",
    "candidate": "promotion_candidate_bundle.json",
    "p0": "p0_promotion_decision.json",
}

HASH_FIELDS = {
    "entry": "evidence_hash",
    "dataset": "dataset_hash",
    "splits": "split_hash",
    "experiment": "registry_hash",
    "commitments": "report_hash",
    "population": "bundle_hash",
    "graph": "report_hash",
    "activation": "report_hash",
    "variants": "manifest_hash",
    "observations": "panel_hash",
    "costs": "panel_hash",
    "receipts": "bundle_hash",
    "qualification": "evidence_hash",
    "candidate": "bundle_hash",
}

GATE_IDS = (
    "P3.INTAKE",
    "P3.DATA",
    "P3.CALIBRATION",
    "P3.EXPERIMENT",
    "P3.SCIENCE",
    "P3.CROSS_PHASE",
    "P3.QUALITY",
    "P3.PROMOTION",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _qualification_file_hashes(evidence_dir: Path) -> dict[str, str]:
    excluded = {FILES["candidate"], FILES["p0"]}
    result: dict[str, str] = {}
    for key, name in FILES.items():
        if name in excluded or key in {"candidate", "p0"}:
            continue
        path = evidence_dir / name
        if path.is_file():
            result[name] = sha256_file(path)
    return result


def _chain_hash(results: list[GateResult] | tuple[GateResult, ...]) -> str:
    qualifying = [item for item in results if item.gate_id != "P3.PROMOTION"]
    return sha256_value([item.model_dump(mode="json") for item in qualifying])


class FinalIntegrationGateEngine:
    def __init__(
        self,
        *,
        release_id: str,
        release_sha256: str,
        keyring: dict[str, PublicKeyRecord],
    ):
        if not valid_sha256(release_sha256):
            raise ValueError("release_sha256 must be a lowercase SHA-256 digest")
        self.release_id = release_id
        self.release_sha256 = release_sha256
        self.keyring = keyring

    def _parse(
        self,
        evidence_dir: Path,
        key: str,
        model: type,
    ) -> tuple[Any | None, list[str], dict[str, str]]:
        path = evidence_dir / FILES[key]
        if not path.is_file():
            return None, [f"missing {FILES[key]}"], {}
        file_hash = {FILES[key]: sha256_file(path)}
        try:
            raw = _load(path)
            value = model.model_validate(raw)
            errors: list[str] = []
            if hasattr(value, "release_id"):
                if value.release_id != self.release_id:
                    errors.append(f"release_id mismatch in {FILES[key]}")
                if value.release_sha256 != self.release_sha256:
                    errors.append(f"release_sha256 mismatch in {FILES[key]}")
            hash_field = HASH_FIELDS.get(key)
            if hash_field:
                claimed = raw.get(hash_field) if isinstance(raw, dict) else None
                if not isinstance(claimed, str) or not valid_sha256(claimed):
                    errors.append(f"missing/invalid {hash_field} in {FILES[key]}")
                else:
                    canonical = dict(raw)
                    canonical[hash_field] = ""
                    actual = sha256_value(canonical)
                    if actual != claimed:
                        errors.append(
                            f"self-hash mismatch in {FILES[key]}: "
                            f"expected={claimed} actual={actual}"
                        )
            return value, errors, file_hash
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            return None, [f"invalid {FILES[key]}: {exc}"], file_hash

    def evaluate(self, evidence_dir: Path) -> IntegrationGateReport:
        evidence_dir = evidence_dir.resolve()
        results: list[GateResult] = []

        entry, errors, hashes = self._parse(
            evidence_dir, "entry", IntegrationEntryEvidence
        )
        if entry is not None:
            required = {
                ReceiptType.PLATFORM_QUALIFICATION,
                ReceiptType.P2_HANDOFF,
                ReceiptType.CHECKPOINT_RELOAD,
                ReceiptType.MODULE_TRACE,
            }
            errors.extend(
                verify_required_receipts(
                    entry.receipts,
                    self.keyring,
                    required,
                    release_id=self.release_id,
                    release_sha256=self.release_sha256,
                )
            )
        results.append(
            GateResult(
                gate_id="P3.INTAKE",
                status=GateStatus.PASS if not errors else GateStatus.NOT_STARTED,
                errors=tuple(errors),
                evidence_hashes=hashes,
            )
        )
        if errors:
            return self._report(results, False)

        dataset, e1, h1 = self._parse(
            evidence_dir, "dataset", EvaluationDatasetManifest
        )
        splits, e2, h2 = self._parse(
            evidence_dir, "splits", EvaluationSplitManifest
        )
        registry, e3, h3 = self._parse(
            evidence_dir, "experiment", ExperimentRegistry
        )
        coverage, e4, h4 = self._parse(
            evidence_dir, "commitments", CommitmentCoverageReport
        )
        errors = e1 + e2 + e3 + e4
        if dataset:
            errors.extend(validate_dataset(dataset))
        if dataset and splits and registry:
            errors.extend(validate_splits(dataset, splits, registry))
        if coverage and registry:
            if coverage.experiment_id != registry.experiment_id:
                errors.append("commitment report experiment mismatch")
            if coverage.status != "PASS" or coverage.coverage_ratio != 1.0:
                errors.append("commitment coverage failed")
        results.append(
            GateResult(
                gate_id="P3.DATA",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=h1 | h2 | h3 | h4,
            )
        )
        if errors:
            return self._report(results, False)

        population, e1, h1 = self._parse(
            evidence_dir, "population", PopulationCalibrationBundle
        )
        graph, e2, h2 = self._parse(
            evidence_dir, "graph", SocialGraphCalibrationReport
        )
        activation, e3, h3 = self._parse(
            evidence_dir, "activation", ActivationTrustSensitivityReport
        )
        errors = e1 + e2 + e3
        if population and graph and activation and registry:
            errors.extend(
                validate_calibration(population, graph, activation, registry)
            )
        results.append(
            GateResult(
                gate_id="P3.CALIBRATION",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=h1 | h2 | h3,
            )
        )
        if errors:
            return self._report(results, False)

        variants, e1, h1 = self._parse(
            evidence_dir, "variants", VariantExecutionManifest
        )
        observations, e2, h2 = self._parse(
            evidence_dir, "observations", EvaluationObservationPanel
        )
        costs, e3, h3 = self._parse(
            evidence_dir, "costs", RuntimeCostLatencyPanel
        )
        errors = e1 + e2 + e3
        if variants and observations and costs and registry and splits:
            errors.extend(
                validate_variant_alignment(
                    variants, observations, costs, registry, splits
                )
            )
        results.append(
            GateResult(
                gate_id="P3.EXPERIMENT",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=h1 | h2 | h3,
            )
        )
        if errors:
            return self._report(results, False)

        scientific = evaluate_real_observations(observations, registry)
        errors = (
            []
            if scientific["all_preregistered_comparisons_passed"]
            else ["preregistered scientific thresholds were not met"]
        )
        results.append(
            GateResult(
                gate_id="P3.SCIENCE",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes={"scientific_report": scientific["report_hash"]},
            )
        )
        if errors:
            return self._report(results, False)

        receipt_bundle, errors, hashes = self._parse(
            evidence_dir, "receipts", CrossPhaseReceiptBundle
        )
        receipts = receipt_bundle.receipts if receipt_bundle else ()
        required = {
            ReceiptType.P4_CONSUMPTION,
            ReceiptType.VARIABLE_EVOLUTION_CONSUMPTION,
            ReceiptType.P9_EVALUATION,
            ReceiptType.P9_FEEDBACK,
            ReceiptType.N_PLUS_1_FEEDBACK,
        }
        if receipt_bundle:
            errors.extend(
                verify_required_receipts(
                    receipts,
                    self.keyring,
                    required,
                    release_id=self.release_id,
                    release_sha256=self.release_sha256,
                )
            )
        results.append(
            GateResult(
                gate_id="P3.CROSS_PHASE",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=hashes,
            )
        )
        if errors:
            return self._report(results, False)

        qualification, errors, hashes = self._parse(
            evidence_dir, "qualification", QualificationSummary
        )
        if qualification:
            if qualification.coverage_percent < 85.0:
                errors.append("whole-source coverage is below 85%")
            for check in qualification.checks:
                path = (evidence_dir / check.evidence_path).resolve()
                try:
                    path.relative_to(evidence_dir)
                except ValueError:
                    errors.append(f"qualification evidence escapes directory: {check.check_id}")
                    continue
                if not path.is_file():
                    errors.append(f"missing qualification evidence: {check.evidence_path}")
                elif sha256_file(path) != check.evidence_sha256:
                    errors.append(f"qualification evidence hash mismatch: {check.check_id}")
        results.append(
            GateResult(
                gate_id="P3.QUALITY",
                status=GateStatus.PASS if not errors else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=hashes,
            )
        )
        if errors:
            return self._report(results, False)

        candidate, candidate_errors, candidate_hashes = self._parse(
            evidence_dir, "candidate", PromotionCandidateBundle
        )
        decision, decision_errors, decision_hashes = self._parse(
            evidence_dir, "p0", P0PromotionDecision
        )
        errors = candidate_errors + decision_errors
        hashes = candidate_hashes | decision_hashes
        promoted = False
        current_chain_hash = _chain_hash(results)
        if candidate and decision:
            if candidate.qualification_chain_hash != current_chain_hash:
                errors.append("candidate does not match the current qualification chain")
            if decision.candidate_bundle_hash != candidate.bundle_hash:
                errors.append("P0 decision does not reference the candidate bundle")
            key = self.keyring.get(decision.key_id)
            if key is None:
                errors.append(f"unknown P0 key_id: {decision.key_id}")
            else:
                if not key.enabled:
                    errors.append(f"disabled P0 key_id: {decision.key_id}")
                if key.authority is not Authority.P0:
                    errors.append("promotion key authority must be P0")
                if not verify_mapping_ed25519(
                    decision.unsigned_payload(), decision.signature, key.public_key
                ):
                    errors.append("invalid P0 decision signature")
            promoted = decision.decision == "PROMOTE" and not errors
        if not promoted and not errors:
            errors.append("P0 did not promote the release")
        results.append(
            GateResult(
                gate_id="P3.PROMOTION",
                status=GateStatus.PASS if promoted else GateStatus.FAIL,
                errors=tuple(errors),
                evidence_hashes=hashes,
            )
        )
        return self._report(results, promoted)

    def build_candidate(
        self,
        evidence_dir: Path,
        report: IntegrationGateReport,
    ) -> PromotionCandidateBundle:
        qualifying = [
            item for item in report.gates if item.gate_id != "P3.PROMOTION"
        ]
        if len(qualifying) != 7 or any(
            item.status is not GateStatus.PASS for item in qualifying
        ):
            raise ValueError("all pre-promotion gates must pass")
        evidence_hashes = _qualification_file_hashes(evidence_dir.resolve())
        payload = {
            "bundle_version": "p3.promotion-candidate.v2",
            "release_id": self.release_id,
            "release_sha256": self.release_sha256,
            "qualification_chain_hash": _chain_hash(qualifying),
            "evidence_hashes": evidence_hashes,
            "created_at": datetime.now(UTC),
            "promotion_authority": "P0_ONLY",
            "production_promotion_allowed": False,
            "bundle_hash": "0" * 64,
        }
        provisional = PromotionCandidateBundle.model_validate(payload)
        normalized = provisional.model_dump(mode="json")
        normalized["bundle_hash"] = ""
        normalized["bundle_hash"] = sha256_value(normalized)
        return PromotionCandidateBundle.model_validate(normalized)

    def _report(
        self,
        results: list[GateResult],
        promoted: bool,
    ) -> IntegrationGateReport:
        if promoted:
            status = GateStatus.PASS
        elif results and results[0].status is GateStatus.NOT_STARTED:
            status = GateStatus.NOT_STARTED
        else:
            status = GateStatus.FAIL
        chain_hash = _chain_hash(results)
        payload = {
            "report_version": "p3.integration-gates.v2",
            "release_id": self.release_id,
            "release_sha256": self.release_sha256,
            "gates": [item.model_dump(mode="json") for item in results],
            "overall_status": status,
            "p0_promotion_validated": promoted,
            "production_promotion_allowed": promoted,
            "generated_at": datetime.now(UTC),
            "qualification_chain_hash": chain_hash,
            "report_hash": "0" * 64,
        }
        provisional = IntegrationGateReport.model_validate(payload)
        normalized = provisional.model_dump(mode="json")
        normalized["report_hash"] = ""
        normalized["report_hash"] = sha256_value(normalized)
        return IntegrationGateReport.model_validate(normalized)


__all__ = ["FinalIntegrationGateEngine", "IntegrationGateReport"]
