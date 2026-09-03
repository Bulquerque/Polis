# P7 subphases

P7 is a sequential decision phase. Each subphase consumes only versioned artifacts from the previous boundary, except S5, which is an isolated offline branch.

## P7.S1 — Boundary and Temporal Integrity

Validate the P6 handoff, reconcile candidate artifacts, enforce point-in-time safety, and load only promoted prior-cycle feedback.

Modules:
- `P7.S1.M01` — `phase6_handoff_contract_validator`
- `P7.S1.M02` — `candidate_artifact_reconciliation_engine`
- `P7.S1.M03` — `temporal_integrity_and_forbidden_field_firewall`
- `P7.S1.M04` — `promoted_ranking_feedback_loader`

## P7.S2 — Eligibility and Comparability

Apply eligibility policies, freeze comparison groups, route metrics with explicit semantics, and publish the runtime foundation handoff.

Modules:
- `P7.S2.M01` — `eligibility_policy_engine`
- `P7.S2.M02` — `comparison_group_builder`
- `P7.S2.M03` — `metric_semantics_router`
- `P7.S2.M04` — `runtime_foundation_handoff_publisher`

## P7.S3 — Dominance, Pareto and Factor Adjustment

Compile comparable metrics, separate common factor exposure, remove strictly dominated candidates, and construct Pareto frontiers.

Modules:
- `P7.S3.M01` — `candidate_metric_semantics_compiler`
- `P7.S3.M02` — `option_factor_exposure_adjuster`
- `P7.S3.M03` — `strict_dominance_filter`
- `P7.S3.M04` — `pareto_frontier_builder`

## P7.S4 — Interpretable Multi-Head Scoring

Bind score policies, calculate interpretable heads, assemble a transparent score, and publish its full decomposition.

Modules:
- `P7.S4.M01` — `scoring_policy_head_binding_compiler`
- `P7.S4.M02` — `multi_head_score_engine`
- `P7.S4.M03` — `interpretable_score_assembler`
- `P7.S4.M04` — `score_decomposition_and_tournament_handoff_publisher`

## P7.S5 — Offline LTR Training and Qualification

Build counterfactual ranking datasets, plan temporal folds, train bounded rankers, and qualify models outside runtime.

Modules:
- `P7.S5.M01` — `ranking_target_policy_registry_builder`
- `P7.S5.M02` — `counterfactual_training_dataset_builder`
- `P7.S5.M03` — `query_group_temporal_split_planner`
- `P7.S5.M04` — `ltr_training_orchestrator`
- `P7.S5.M05` — `ltr_model_qualification_gate`

## P7.S6 — Runtime Scoring and Hybrid Blend

Validate promoted model compatibility, score by comparison group, calibrate confidence, and blend with the interpretable baseline.

Modules:
- `P7.S6.M01` — `runtime_model_compatibility_gate`
- `P7.S6.M02` — `group_aware_ltr_runtime_scorer`
- `P7.S6.M03` — `score_calibration_confidence_engine`
- `P7.S6.M04` — `hybrid_score_blend_and_handoff_builder`

## P7.S7 — Similarity, Diversity, Safety and Abstention

Measure candidate similarity, reduce redundant concentration, enforce material safety, and abstain when evidence is insufficient.

Modules:
- `P7.S7.M01` — `candidate_similarity_graph_builder`
- `P7.S7.M02` — `diversity_adjustment_engine`
- `P7.S7.M03` — `final_candidate_safety_gate`
- `P7.S7.M04` — `abstention_and_rankability_gate`

## P7.S8 — Deterministic Ranking and P8 Publication

Rank deterministically within groups, publish structured theses and traces, preserve execution context, and close the P8 handoff.

Modules:
- `P7.S8.M01` — `deterministic_group_ranking_engine`
- `P7.S8.M02` — `thesis_card_and_ranking_audit_builder`
- `P7.S8.M03` — `phase8_strategy_ranking_handoff_builder`
- `P7.S8.M04` — `phase8_handoff_and_release_publisher`
