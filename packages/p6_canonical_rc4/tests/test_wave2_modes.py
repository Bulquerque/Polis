from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    CapabilityStatus,
    SolverStatus,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import (
    canonical_sha256,
)
from quant_pipeline.phase_06_strategy_synthesis.orchestration.phase_runner import (
    run_phase,
)


def advanced_configuration(configuration, mode="INVERSE_DESIGN"):
    value = deepcopy(configuration)
    value["operational_mode"] = mode
    value["budgets"] = {
        "max_solver_seconds": 1,
        "max_solver_nodes": 500,
        "max_mutations": 20,
    }
    value["solver"] = {
        "evolutionary_population": 6,
        "evolutionary_generations": 2,
    }
    return value


def test_template_mode_remains_independent(inputs, configuration):
    result = run_phase(inputs, configuration)
    assert result["outputs"]["target_payoff_panel"].record_count == 0
    assert result["outputs"]["solver_result_panel"].record_count == 0
    assert result["outputs"]["mutated_strategy_candidate_panel"].record_count == 0
    assert result["canonical_outputs"]["strategy_candidate_panel"].record_count > 0


def test_mutation_mode_generates_bounded_children(inputs, configuration):
    config = advanced_configuration(configuration, "TEMPLATE_MUTATION")
    result = run_phase(inputs, config)
    mutations = result["outputs"]["mutation_application_panel"].records
    candidates = result["outputs"]["mutated_strategy_candidate_panel"].records
    assert mutations
    assert candidates
    assert len(candidates) <= config["budgets"]["max_mutations"]
    assert all(item.valid for item in mutations)
    parent_ids = {
        item.candidate_id
        for item in result["outputs"]["template_strategy_candidate_panel"].records
    }
    assert all(item.parent_candidate_id in parent_ids for item in mutations)


def test_target_payoffs_are_aligned_finite_and_regularized(inputs, configuration):
    result = run_phase(inputs, advanced_configuration(configuration))
    targets = result["outputs"]["target_payoff_panel"].records
    qualifications = {
        item.target_payoff_id: item
        for item in result["outputs"]["target_payoff_qualification_report"].records
    }
    assert targets
    for target in targets:
        assert len(target.terminal_state_grid) == len(target.regularized_target_payoff)
        assert sum(target.scenario_probabilities, Decimal("0")) == Decimal("1")
        assert qualifications[target.target_payoff_id].qualified


def test_market_implied_state_preserves_probability_mass(inputs, configuration):
    result = run_phase(inputs, advanced_configuration(configuration))
    state = result["outputs"]["market_implied_state_panel"].records[0]
    if state.status.value == "AVAILABLE":
        assert sum(state.risk_neutral_probabilities, Decimal("0")) == Decimal("1")
        assert len(state.state_grid) == len(state.risk_neutral_probabilities)


def test_inverse_design_never_uses_phantom_instruments(inputs, configuration):
    result = run_phase(inputs, advanced_configuration(configuration))
    universe = {
        row["contract_id"]
        for row in inputs["clean_option_contract_panel"]["records"]
    }
    universe.add("XYZ")
    candidates = result["outputs"]["inverse_strategy_candidate_panel"].records
    assert candidates
    for candidate in candidates:
        assert {leg.instrument_id for leg in candidate.legs} <= universe
        sides = {}
        for leg in candidate.legs:
            sides.setdefault(leg.instrument_id, set()).add(leg.side.value)
        assert all(len(values) == 1 for values in sides.values())


def test_solver_timeout_is_not_reported_as_optimal(inputs, configuration):
    config = advanced_configuration(configuration)
    config["budgets"]["max_solver_nodes"] = 1
    result = run_phase(inputs, config)
    records = result["outputs"]["mixed_integer_solver_result_panel"].records
    assert records
    assert any(item.status is SolverStatus.TIMEOUT for item in records)
    assert all(
        not (item.timeout and item.status is SolverStatus.OPTIMAL)
        for item in records
    )


def test_published_candidates_have_defined_risk(inputs, configuration):
    result = run_phase(inputs, advanced_configuration(configuration))
    candidate_ids = {
        item.candidate_id
        for item in result["canonical_outputs"]["strategy_candidate_panel"].records
    }
    qualifications = {
        item.candidate_id: item
        for item in result["outputs"]["strategy_qualification_panel"].records
    }
    assert candidate_ids
    assert all(qualifications[item].qualified for item in candidate_ids)
    assert all(qualifications[item].maximum_loss_proven for item in candidate_ids)


def test_advanced_replay_is_deterministic(inputs, configuration):
    config = advanced_configuration(configuration)
    first = run_phase(deepcopy(inputs), deepcopy(config))
    second = run_phase(deepcopy(inputs), deepcopy(config))
    names = (
        "strategy_candidate_panel",
        "target_payoff_panel",
        "solver_result_panel",
        "quality_diversity_archive",
    )
    for name in names:
        assert first["canonical_outputs"][name].content_sha256 == second["canonical_outputs"][name].content_sha256


def test_challenger_is_seeded_and_non_blocking(inputs, configuration):
    config = advanced_configuration(configuration, "CHALLENGER")
    first = run_phase(deepcopy(inputs), deepcopy(config))
    second = run_phase(deepcopy(inputs), deepcopy(config))
    challenger = first["outputs"]["evolutionary_solver_result_panel"]
    assert challenger.record_count > 0
    assert challenger.content_sha256 == second["outputs"]["evolutionary_solver_result_panel"].content_sha256
    assert first["canonical_outputs"]["strategy_candidate_panel"].record_count > 0


def test_pathwise_and_ambiguity_are_used_only_when_supplied(inputs, configuration):
    modified = deepcopy(inputs)
    belief = modified["market_belief_state"]["records"][0]
    belief["ambiguity_capability"] = "AVAILABLE"
    belief["ambiguity_set_id"] = "ambiguity-xyz"
    belief["ambiguity_probabilities"] = [
        ["0.35", "0.5", "0.15"],
        ["0.1", "0.4", "0.5"],
    ]
    for scenario in belief["scenarios"]:
        terminal = Decimal(scenario["terminal_underlying_price"])
        scenario["path_prices"] = [
            "100",
            str((Decimal("100") + terminal) / Decimal("2")),
            str(terminal),
        ]
    modified["market_belief_state"]["content_sha256"] = canonical_sha256(
        modified["market_belief_state"]["records"]
    )
    result = run_phase(modified, advanced_configuration(configuration))
    assert result["outputs"]["pathwise_valuation_panel"].record_count > 0
    ambiguity = result["canonical_outputs"]["strategy_ambiguity_evaluation_panel"]
    assert ambiguity.record_count > 0
    assert all(item.status is CapabilityStatus.AVAILABLE for item in ambiguity.records)
    assert all(item.worst_case_expected_payoff is not None for item in ambiguity.records)


def test_quality_diversity_reports_coverage_not_global_rank(inputs, configuration):
    result = run_phase(inputs, advanced_configuration(configuration, "QUALITY_DIVERSITY"))
    report = result["canonical_outputs"]["quality_diversity_report"].records[0]
    assert Decimal("0") <= report.coverage <= Decimal("1")
    assert report.niches_filled == result["canonical_outputs"]["quality_diversity_archive"].record_count
    assert "rank" not in report.model_dump()
