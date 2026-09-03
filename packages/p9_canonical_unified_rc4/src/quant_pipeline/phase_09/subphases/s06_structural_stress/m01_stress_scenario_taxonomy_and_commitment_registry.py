from __future__ import annotations

from .contracts import S6State, content_sha256
from .models import (
    CommittedScenario,
    MaterialRiskCoverage,
    ScenarioProposal,
    ScenarioRegistryRequest,
    StressScenarioRegistrySnapshot,
)


def _semantic_payload(proposal: ScenarioProposal) -> dict[str, object]:
    return {
        "scenario_class": proposal.scenario_class,
        "purpose": proposal.purpose,
        "approved_uses": tuple(sorted(proposal.approved_uses)),
        "prohibited_uses": tuple(sorted(proposal.prohibited_uses)),
        "shocks": tuple(
            sorted(
                ((shock.factor_id, shock.value, shock.unit) for shock in proposal.shocks),
                key=lambda row: row[0],
            )
        ),
        "horizon_days": proposal.horizon_days,
        "severity_label": proposal.severity_label,
        "plausibility_label": proposal.plausibility_label,
    }


def _commitment_error(request: ScenarioRegistryRequest, proposal: ScenarioProposal) -> str | None:
    if proposal.created_at > request.context.decision_time:
        return "P9_STRESS_SCENARIO_FUTURE_TIMESTAMP"
    if (
        request.policy.reject_post_outcome_commitment
        and request.outcome_results_observed_at is not None
        and proposal.created_at >= request.outcome_results_observed_at
    ):
        return "P9_STRESS_SCENARIO_POST_OUTCOME"
    return None


def _commit_proposals(
    request: ScenarioRegistryRequest,
) -> tuple[list[CommittedScenario], list[str], list[str]]:
    committed: list[CommittedScenario] = []
    duplicates: list[str] = []
    reason_codes: list[str] = []
    seen: dict[str, str] = {}
    for proposal in request.proposals:
        error = _commitment_error(request, proposal)
        if error is not None:
            reason_codes.append(error)
            continue
        semantic_hash = content_sha256(_semantic_payload(proposal))
        if semantic_hash in seen:
            duplicates.append(proposal.scenario_id)
            reason_codes.append("P9_STRESS_SCENARIO_DUPLICATE")
            if request.policy.duplicate_semantic_hash_rejected:
                continue
        seen[semantic_hash] = proposal.scenario_id
        committed.append(CommittedScenario(scenario=proposal, semantic_sha256=semantic_hash))
    return committed, duplicates, reason_codes


def _risk_coverage(
    request: ScenarioRegistryRequest,
    committed: list[CommittedScenario],
) -> tuple[tuple[MaterialRiskCoverage, ...], float]:
    factors_by_scenario = {
        item.scenario.scenario_id: {shock.factor_id for shock in item.scenario.shocks}
        for item in committed
    }
    rows: list[MaterialRiskCoverage] = []
    covered_weight = 0.0
    total_weight = sum(risk.materiality_weight for risk in request.material_risks)
    for risk in request.material_risks:
        covering = tuple(
            scenario_id
            for scenario_id, factor_ids in factors_by_scenario.items()
            if set(risk.factor_ids) & factor_ids
        )
        if covering:
            covered_weight += risk.materiality_weight
        rows.append(
            MaterialRiskCoverage(
                risk_id=risk.risk_id,
                covered=bool(covering),
                covering_scenario_ids=covering,
                materiality_weight=risk.materiality_weight,
            )
        )
    coverage = 1.0 if total_weight == 0 else covered_weight / total_weight
    return tuple(rows), coverage


def _registry_status(
    committed: list[CommittedScenario],
    coverage: float,
    minimum_coverage: float,
) -> S6State:
    if not committed:
        return S6State.INVALID
    if coverage < minimum_coverage:
        return S6State.COMMITTED_WITH_COVERAGE_GAPS
    return S6State.COMMITTED


def build_scenario_registry(request: ScenarioRegistryRequest) -> StressScenarioRegistrySnapshot:
    """Commit immutable scenarios and compute weighted material-risk coverage."""

    committed, duplicates, reason_codes = _commit_proposals(request)
    coverage_rows, coverage = _risk_coverage(request, committed)
    limitations: list[str] = []
    if coverage < request.policy.minimum_material_risk_coverage:
        reason_codes.append("P9_STRESS_MATERIAL_RISK_UNCOVERED")
        limitations.append("material-risk coverage is below the committed policy threshold")
    status = _registry_status(
        committed,
        coverage,
        request.policy.minimum_material_risk_coverage,
    )
    payload = {
        "context": request.context.model_dump(mode="json"),
        "s5_qualification": request.s5_qualification.model_dump(mode="json"),
        "scenarios": [item.model_dump(mode="json") for item in committed],
        "coverage": [item.model_dump(mode="json") for item in coverage_rows],
        "duplicates": duplicates,
    }
    registry_hash = content_sha256(payload)
    return StressScenarioRegistrySnapshot(
        status=status,
        registry_id=f"{request.context.run_id}:P9.S6.SCENARIOS:{registry_hash[:16]}",
        scenarios=tuple(committed),
        duplicate_scenario_ids=tuple(duplicates),
        risk_coverage=coverage_rows,
        weighted_material_risk_coverage=coverage,
        commitment_time=request.context.decision_time,
        registry_sha256=registry_hash,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        limitations=tuple(limitations),
    )
