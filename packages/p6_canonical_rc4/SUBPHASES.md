# Subphases

## P6.S1 — Boundary and Market Snapshot

- `P6.S1.M01` — `p5_belief_handoff_validator`
- `P6.S1.M02` — `option_market_input_validator`
- `P6.S1.M03` — `underlying_market_input_validator`
- `P6.S1.M04` — `static_arbitrage_diagnostic`
- `P6.S1.M05` — `pit_market_snapshot_builder`

## P6.S2 — Canonical Strategy Domain

- `P6.S2.M01` — `contract_existence_gate`
- `P6.S2.M02` — `strategy_grammar_registry`
- `P6.S2.M03` — `objective_family_registry`
- `P6.S2.M04` — `constraint_policy_registry`
- `P6.S2.M05` — `strategy_identity_builder`

## P6.S3 — Template Generation

- `P6.S3.M01` — `single_instrument_generator`
- `P6.S3.M02` — `vertical_generator`
- `P6.S3.M03` — `volatility_structure_generator`
- `P6.S3.M04` — `skew_asymmetric_generator`
- `P6.S3.M05` — `term_structure_generator`
- `P6.S3.M06` — `underlying_overlay_generator`
- `P6.S3.M07` — `template_parameter_planner`

## P6.S4 — Mutation and Deformation

- `P6.S4.M01` — `mutation_operator_registry`
- `P6.S4.M02` — `local_mutation_engine`
- `P6.S4.M03` — `mutation_trace_validator`
- `P6.S4.M04` — `complexity_budget_gate`

## P6.S5 — Target Payoff and Market-Implied State

- `P6.S5.M01` — `market_implied_state_estimator`
- `P6.S5.M02` — `belief_to_payoff_transformer`
- `P6.S5.M03` — `target_payoff_regularizer`
- `P6.S5.M04` — `target_payoff_qualification_gate`

## P6.S6 — Inverse Design and Solver Portfolio

- `P6.S6.M01` — `replication_basis_builder`
- `P6.S6.M02` — `continuous_relaxation_solver`
- `P6.S6.M03` — `mixed_integer_solver`
- `P6.S6.M04` — `beam_search_solver`
- `P6.S6.M05` — `local_search_solver`
- `P6.S6.M06` — `evolutionary_challenger`
- `P6.S6.M07` — `solver_portfolio_orchestrator`

## P6.S7 — Pricing, Greeks and Scenario Evaluation

- `P6.S7.M01` — `entry_price_engine`
- `P6.S7.M02` — `terminal_payoff_engine`
- `P6.S7.M03` — `pathwise_valuation_engine`
- `P6.S7.M04` — `greek_engine`
- `P6.S7.M05` — `break_even_shape_engine`
- `P6.S7.M06` — `scenario_evaluator`
- `P6.S7.M07` — `ambiguity_evaluator`

## P6.S8 — Feasibility and Defined-Risk Gate

- `P6.S8.M01` — `structural_validator`
- `P6.S8.M02` — `maximum_loss_prover`
- `P6.S8.M03` — `margin_feasibility_gate`
- `P6.S8.M04` — `liquidity_gate`
- `P6.S8.M05` — `cost_gate`
- `P6.S8.M06` — `data_quality_gate`
- `P6.S8.M07` — `economic_sanity_gate`

## P6.S9 — Canonicalization, Equivalence and Quality-Diversity

- `P6.S9.M01` — `leg_canonicalizer`
- `P6.S9.M02` — `relative_scale_normalizer`
- `P6.S9.M03` — `payoff_fingerprint_builder`
- `P6.S9.M04` — `economic_fingerprint_builder`
- `P6.S9.M05` — `equivalence_clustering`
- `P6.S9.M06` — `representative_selector`

## P6.S10 — Qualification, Publication and P7 Handoff

- `P6.S10.M01` — `canonical_strategy_publisher`
- `P6.S10.M02` — `p7_v1_projection_builder`
- `P6.S10.M03` — `phase7_handoff_manifest_builder`
