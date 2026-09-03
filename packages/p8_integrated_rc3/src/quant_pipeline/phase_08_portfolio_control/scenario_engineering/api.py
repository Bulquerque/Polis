"""Public orchestration API for the complete P8.S3 subphase."""
from __future__ import annotations

from pathlib import Path

from .artifact_store import ArtifactWriter
from .contracts import (
    ModuleReceipt, S3Request, S3Result, ScenarioSetSummary,
)
from .hashing import canonical_sha256
from .modules.ambiguity_compiler import compile_ambiguity
from .modules.distribution_resolver import resolve_distribution
from .modules.quality_gate import assess_quality
from .modules.scenario_materializer import materialize_scenarios
from .modules.scenario_reduction import reduce_scenarios
from .modules.stress_factory import build_stresses, find_reverse_stress, make_stress_result
from .ports import DecisionEvaluationPort, RiskResponseEvaluatorPort


def _summary(scenarios, storage: str | None = None) -> ScenarioSetSummary:
    count, steps, factors = scenarios.shape
    digest = scenarios.content_sha256()
    return ScenarioSetSummary(
        artifact_id=f"scenario-{digest[:16]}", scenario_count=count, step_count=steps,
        factor_count=factors, probability_sum=float(scenarios.probabilities.sum()),
        content_sha256=digest, storage_npz=storage,
    )


def _receipt(module_id: str, input_value, output_value, status: str = "PASS", reasons=()) -> ModuleReceipt:
    return ModuleReceipt(
        module_id=module_id, input_sha256=canonical_sha256(input_value),
        output_sha256=canonical_sha256(output_value), status=status, reason_codes=tuple(reasons),
    )


def run_s3(
    request: S3Request,
    output_dir: Path | None = None,
    decision_evaluator: DecisionEvaluationPort | None = None,
    risk_evaluator: RiskResponseEvaluatorPort | None = None,
    reverse_stress_base_shock: tuple[float, ...] | None = None,
) -> S3Result:
    receipts: list[ModuleReceipt] = []
    resolution = resolve_distribution(request.belief)
    receipts.append(_receipt("P8.S3.M01", request.belief, resolution))
    full = materialize_scenarios(request.belief, request.scenario_policy, request.historical_scenarios)
    receipts.append(_receipt("P8.S3.M02", request.scenario_policy, {"sha256": full.content_sha256()}))
    quality = assess_quality(full, request.realized_samples, request.strategy_families, request.quality_policy)
    q_status = "PASS" if quality.score >= 0.5 else "DEGRADED"
    receipts.append(_receipt("P8.S3.M03", request.quality_policy, quality, q_status, quality.reason_codes))
    stresses = build_stresses(full, request.stress_policy)
    base_shock = reverse_stress_base_shock or tuple(0.0 for _ in full.factor_ids)
    if risk_evaluator is None:
        reverse = ("CAPABILITY_UNAVAILABLE", None, ())
    else:
        reverse = find_reverse_stress(base_shock, risk_evaluator, request.stress_policy)
    stress_result = make_stress_result(stresses, *reverse)
    stress_status = "PASS" if reverse[0] == "COMPUTED" else "CAPABILITY_UNAVAILABLE"
    receipts.append(_receipt("P8.S3.M04", request.stress_policy, stress_result, stress_status))
    reduced, reduction = reduce_scenarios(full, request.reduction_policy, decision_evaluator)
    reduction_status = "PASS" if reduction.status.value == "SAFE" else "DEGRADED"
    receipts.append(_receipt("P8.S3.M05", request.reduction_policy, reduction, reduction_status, (reduction.status.value,)))
    ambiguity = compile_ambiguity(
        reduced, quality, reduction, request.belief.calibration_score,
        request.belief.ood_score, request.belief.disagreement_score,
        request.ordinal_risk_cap, request.actionability_policy,
    )
    ambiguity_status = "NO_ACTION_VALID" if ambiguity.actionability_state.value == "NO_ACTION_VALID" else "PASS"
    receipts.append(_receipt("P8.S3.M06", request.actionability_policy, ambiguity, ambiguity_status, ambiguity.reason_codes))
    full_storage = reduced_storage = None
    if output_dir is not None:
        writer = ArtifactWriter(output_dir)
        full_storage = writer.write_scenario_set("full_scenarios", full)
        reduced_storage = writer.write_scenario_set("reduced_scenarios", reduced)
        writer.write_stress_set("stress_scenarios", stresses)
    result_without_hash = {
        "run_id": request.run_id, "cycle_id": request.cycle_id,
        "resolution": resolution, "full_scenarios": _summary(full, full_storage),
        "quality": quality, "stress": stress_result,
        "reduced_scenarios": _summary(reduced, reduced_storage),
        "reduction": reduction, "ambiguity": ambiguity, "receipts": tuple(receipts),
    }
    result = S3Result(**result_without_hash, result_sha256=canonical_sha256(result_without_hash))
    if output_dir is not None:
        ArtifactWriter(output_dir).write_model("s3_result", result)
    return result
