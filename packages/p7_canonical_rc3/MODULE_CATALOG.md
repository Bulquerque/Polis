# P7 module catalog

All 33 modules use the public `run_module(inputs, config)` boundary. Business logic lives in named services and policies; wrappers remain orchestration-only.

## P7.S1.M01 — `phase6_handoff_contract_validator`

Validate the complete P6 manifest and referenced artifact envelopes before record consumption.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S1_M01_phase6_handoff_contract_validator.py`

**Inputs**

- `phase7_strategy_handoff_manifest`
- `declared_p6_artifacts`

**Outputs**

- `verified_p6_artifact_index`
- `p6_handoff_validation_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S1.M02 — `candidate_artifact_reconciliation_engine`

Reconcile candidate, leg, payoff, scenario, risk, cost and lineage records into one validated candidate bundle.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S1_M02_candidate_artifact_reconciliation_engine.py`

**Inputs**

- `verified_p6_artifact_index`

**Outputs**

- `validated_strategy_candidate_bundle`
- `candidate_reconciliation_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S1.M03 — `temporal_integrity_and_forbidden_field_firewall`

Reject future-dated evidence and recursively scan candidate records for forbidden outcome fields.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S1_M03_temporal_integrity_and_forbidden_field_firewall.py`

**Inputs**

- `validated_strategy_candidate_bundle`

**Outputs**

- `temporally_safe_candidate_bundle`
- `temporal_integrity_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S1.M04 — `promoted_ranking_feedback_loader`

Load only promoted, previous-cycle ranking feedback and preserve absence explicitly.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S1_M04_promoted_ranking_feedback_loader.py`

**Inputs**

- `ranking_feedback_report`
- `ranking_feedback_manifest`

**Outputs**

- `ranking_feedback_context`
- `feedback_validation_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S2.M01 — `eligibility_policy_engine`

Evaluate candidate eligibility from versioned policies without inventing economic values.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S2_M01_eligibility_policy_engine.py`

**Inputs**

- `temporally_safe_candidate_bundle`
- `ranking_feedback_context`
- `eligibility_policy_registry`

**Outputs**

- `eligible_strategy_candidate_panel`
- `eligibility_blocked_candidate_panel`
- `eligibility_decision_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S2.M02 — `comparison_group_builder`

Create deterministic groups of economically comparable candidates and verify group coverage.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S2_M02_comparison_group_builder.py`

**Inputs**

- `eligible_strategy_candidate_panel`
- `comparison_group_policy`

**Outputs**

- `candidate_comparison_group_panel`
- `comparison_group_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S2.M03 — `metric_semantics_router`

Route candidate metrics with explicit unit, direction, transformation, availability and missingness semantics.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S2_M03_metric_semantics_router.py`

**Inputs**

- `eligible_strategy_candidate_panel`
- `candidate_comparison_group_panel`
- `metric_semantics_registry`
- `objective_family_registry`

**Outputs**

- `candidate_metric_route_panel`
- `metric_semantics_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S2.M04 — `runtime_foundation_handoff_publisher`

Publish a content-addressed handoff covering eligible, blocked, grouped and routed candidates.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/foundation/modules/P7_S2_M04_runtime_foundation_handoff_publisher.py`

**Inputs**

- `eligible_strategy_candidate_panel`
- `eligibility_blocked_candidate_panel`
- `eligibility_decision_panel`
- `candidate_comparison_group_panel`
- `candidate_metric_route_panel`
- `ranking_feedback_context`

**Outputs**

- `runtime_foundation_handoff_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S3.M01 — `candidate_metric_semantics_compiler`

Compile routed metrics into a comparable semantic space while preserving raw values and absence.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S3_M01_candidate_metric_semantics_compiler.py`

**Inputs**

- `runtime_foundation_handoff_manifest`
- `eligible_strategy_candidate_panel`
- `candidate_comparison_group_panel`
- `candidate_metric_source_panel`
- `ranking_policy_context`
- `runtime_foundation_audit_report`

**Outputs**

- `comparable_candidate_metric_panel`
- `metric_semantics_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S3.M02 — `option_factor_exposure_adjuster`

Estimate common option-factor exposure and preserve residual edge as a distinct metric.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S3_M02_option_factor_exposure_adjuster.py`

**Inputs**

- `comparable_candidate_metric_panel`
- `eligible_strategy_candidate_panel`
- `ranking_policy_context`
- `runtime_foundation_audit_report`
- `option_factor_model_artifact`

**Outputs**

- `factor_adjusted_metric_panel`
- `factor_exposure_panel`
- `factor_adjustment_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S3.M03 — `strict_dominance_filter`

Remove only candidates that are strictly dominated under compatible metrics and policies.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S3_M03_strict_dominance_filter.py`

**Inputs**

- `factor_adjusted_metric_panel`
- `comparable_candidate_metric_panel`
- `candidate_comparison_group_panel`
- `ranking_policy_context`
- `runtime_foundation_audit_report`

**Outputs**

- `dominance_relation_panel`
- `dominated_candidate_panel`
- `dominance_survivor_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S3.M04 — `pareto_frontier_builder`

Construct deterministic Pareto layers for each comparison group and preserve incomparable trade-offs.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S3_M04_pareto_frontier_builder.py`

**Inputs**

- `dominance_relation_panel`
- `dominated_candidate_panel`
- `dominance_survivor_panel`
- `factor_adjusted_metric_panel`
- `ranking_policy_context`
- `runtime_foundation_audit_report`

**Outputs**

- `pareto_frontier_panel`
- `pareto_frontier_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S4.M01 — `scoring_policy_head_binding_compiler`

Bind Pareto candidates and metric semantics to versioned interpretable scoring heads.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S4_M01_scoring_policy_head_binding_compiler.py`

**Inputs**

- `pareto_frontier_panel`
- `factor_adjusted_metric_panel`
- `comparable_candidate_metric_panel`
- `candidate_comparison_group_panel`
- `scoring_policy_context`

**Outputs**

- `scoring_head_input_panel`
- `scoring_policy_receipt`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S4.M02 — `multi_head_score_engine`

Calculate belief-fit, edge, downside, execution and robustness heads with explicit contributions.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S4_M02_multi_head_score_engine.py`

**Inputs**

- `scoring_head_input_panel`
- `factor_adjusted_metric_panel`
- `comparable_candidate_metric_panel`
- `scoring_policy_receipt`

**Outputs**

- `scoring_head_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S4.M03 — `interpretable_score_assembler`

Assemble normalized head contributions into an interpretable candidate score.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S4_M03_interpretable_score_assembler.py`

**Inputs**

- `scoring_head_panel`
- `scoring_policy_receipt`
- `pareto_frontier_panel`

**Outputs**

- `interpretable_score_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S4.M04 — `score_decomposition_and_tournament_handoff_publisher`

Publish complete score decomposition, tournament audit evidence and the learning handoff.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/tournament/modules/P7_S4_M04_score_decomposition_and_tournament_handoff_publisher.py`

**Inputs**

- `interpretable_score_panel`
- `scoring_head_panel`
- `scoring_policy_receipt`
- `pareto_frontier_panel`
- `pareto_frontier_audit_report`
- `dominated_candidate_panel`
- `dominance_survivor_panel`
- `dominance_relation_panel`
- `factor_adjusted_metric_panel`
- `factor_exposure_panel`
- `comparable_candidate_metric_panel`
- `metric_semantics_audit_report`
- `factor_adjustment_audit_report`

**Outputs**

- `score_decomposition_panel`
- `interpretable_tournament_audit_report`
- `interpretable_tournament_handoff_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S5.M01 — `ranking_target_policy_registry_builder`

Compile versioned ranking target definitions without exposing future outcomes to runtime.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S5_M01_ranking_target_policy_registry_builder.py`

**Inputs**

- `ranking_target_policy_source`
- `metric_semantics_registry`

**Outputs**

- `ranking_target_policy_registry`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S5.M02 — `counterfactual_training_dataset_builder`

Build grouped counterfactual training evidence for all evaluable historical candidates.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S5_M02_counterfactual_training_dataset_builder.py`

**Inputs**

- `historical_tournament_snapshots`
- `historical_candidate_counterfactual_outcome_panel`
- `ranking_target_policy_registry`

**Outputs**

- `ltr_training_dataset_manifest`
- `ltr_query_group_panel`
- `label_coverage_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S5.M03 — `query_group_temporal_split_planner`

Create purged and embargoed temporal folds using the trading calendar and query groups.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S5_M03_query_group_temporal_split_planner.py`

**Inputs**

- `ltr_training_dataset_manifest`
- `trading_calendar_reference`

**Outputs**

- `ltr_temporal_fold_plan`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S5.M04 — `ltr_training_orchestrator`

Train bounded pointwise and pairwise ranking baselines and publish out-of-fold evidence.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S5_M04_ltr_training_orchestrator.py`

**Inputs**

- `ltr_training_dataset_manifest`
- `ltr_temporal_fold_plan`
- `model_family_registry`

**Outputs**

- `ltr_model_artifact`
- `ltr_oof_score_panel`
- `ltr_calibration_evidence_panel`
- `training_execution_receipt`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S5.M05 — `ltr_model_qualification_gate`

Compare rankers against the interpretable baseline and publish runtime eligibility evidence.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S5_M05_ltr_model_qualification_gate.py`

**Inputs**

- `ltr_model_artifact`
- `ltr_oof_score_panel`
- `ltr_calibration_evidence_panel`
- `training_execution_receipt`
- `interpretable_baseline_history`

**Outputs**

- `ltr_model_qualification_report`
- `ltr_model_qualification_registry`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S6.M01 — `runtime_model_compatibility_gate`

Accept only governed, qualified and temporally compatible model artifacts.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S6_M01_runtime_model_compatibility_gate.py`

**Inputs**

- `interpretable_tournament_handoff_manifest`
- `tournament_artifacts`
- `ltr_model_artifact`
- `ltr_model_qualification_registry`
- `governed_model_registry`

**Outputs**

- `runtime_model_compatibility_report`
- `resolved_runtime_model_reference`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S6.M02 — `group_aware_ltr_runtime_scorer`

Score candidates within their comparison groups without training or future access.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S6_M02_group_aware_ltr_runtime_scorer.py`

**Inputs**

- `factor_adjusted_candidate_panel`
- `ltr_model_artifact`
- `resolved_runtime_model_reference`
- `runtime_model_compatibility_report`

**Outputs**

- `ltr_model_score_panel`
- `model_runtime_receipt`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S6.M03 — `score_calibration_confidence_engine`

Calibrate runtime LTR scores and publish confidence only when supporting evidence exists.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S6_M03_score_calibration_confidence_engine.py`

**Inputs**

- `factor_adjusted_candidate_panel`
- `ltr_model_score_panel`
- `ltr_model_artifact`
- `resolved_runtime_model_reference`
- `ltr_model_qualification_report`

**Outputs**

- `ltr_score_calibration_panel`
- `ltr_score_confidence_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S6.M04 — `hybrid_score_blend_and_handoff_builder`

Blend calibrated LTR evidence with the interpretable baseline, preserve fallback, and publish final scoring evidence.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/learning/modules/P7_S6_M04_hybrid_score_blend_and_handoff_builder.py`

**Inputs**

- `interpretable_score_panel`
- `interpretable_score_decomposition_panel`
- `ltr_model_score_panel`
- `ltr_score_calibration_panel`
- `ltr_score_confidence_panel`
- `runtime_model_compatibility_report`

**Outputs**

- `hybrid_candidate_score_panel`
- `hybrid_score_decomposition_panel`
- `learning_candidate_conservation_report`
- `hybrid_scoring_handoff_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S7.M01 — `candidate_similarity_graph_builder`

Build a sparse graph from payoff, scenario, Greek, leg, template and expiry similarity.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S7_M01_candidate_similarity_graph_builder.py`

**Inputs**

- `hybrid_scoring_handoff_manifest`
- `validated_strategy_candidate_reference_panel`
- `hybrid_candidate_score_panel`

**Outputs**

- `candidate_similarity_edge_panel`
- `candidate_similarity_summary_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S7.M02 — `diversity_adjustment_engine`

Cluster similar candidates and apply a bounded, deterministic redundancy adjustment.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S7_M02_diversity_adjustment_engine.py`

**Inputs**

- `hybrid_scoring_handoff_manifest`
- `validated_strategy_candidate_reference_panel`
- `hybrid_candidate_score_panel`
- `candidate_similarity_edge_panel`

**Outputs**

- `candidate_diversity_cluster_panel`
- `diversity_adjustment_panel`
- `diversity_adjusted_score_panel`
- `diversity_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S7.M03 — `final_candidate_safety_gate`

Block materially invalid candidates using finite-score, context, cost, liquidity and upstream evidence rules.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S7_M03_final_candidate_safety_gate.py`

**Inputs**

- `hybrid_scoring_handoff_manifest`
- `validated_strategy_candidate_reference_panel`
- `diversity_adjusted_score_panel`
- `pre_final_blocked_candidate_panel`

**Outputs**

- `safety_eligible_candidate_panel`
- `safety_blocked_candidate_panel`
- `safety_gate_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S7.M04 — `abstention_and_rankability_gate`

Separate rankable candidates from valid candidates with insufficient confidence, OOD evidence or group coverage.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S7_M04_abstention_and_rankability_gate.py`

**Inputs**

- `hybrid_scoring_handoff_manifest`
- `validated_strategy_candidate_reference_panel`
- `safety_eligible_candidate_panel`
- `safety_blocked_candidate_panel`
- `candidate_score_confidence_panel`

**Outputs**

- `rankable_candidate_panel`
- `abstained_candidate_panel`
- `final_blocked_candidate_panel`
- `rankability_group_report`
- `rankability_handoff_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S8.M01 — `deterministic_group_ranking_engine`

Order rankable candidates within each comparison group with deterministic economic tie-breaking.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S8_M01_deterministic_group_ranking_engine.py`

**Inputs**

- `rankability_handoff_manifest`
- `rankable_candidate_panel`
- `diversity_adjusted_score_panel`
- `candidate_score_confidence_panel`

**Outputs**

- `ranked_strategy_candidate_panel`
- `ranking_tie_report`
- `ranking_group_summary_panel`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S8.M02 — `thesis_card_and_ranking_audit_builder`

Publish structured strategy theses, trace records and complete ranking audit evidence.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S8_M02_thesis_card_and_ranking_audit_builder.py`

**Inputs**

- `rankability_handoff_manifest`
- `ranked_strategy_candidate_panel`
- `score_decomposition_panel`
- `validated_strategy_candidate_reference_panel`

**Outputs**

- `strategy_thesis_card_panel`
- `ranking_trace_panel`
- `ranking_audit_report`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S8.M03 — `phase8_strategy_ranking_handoff_builder`

Join ranked candidates to immutable P6 execution-context references and publish the P8 contract.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S8_M03_phase8_strategy_ranking_handoff_builder.py`

**Inputs**

- `ranked_strategy_candidate_panel`
- `strategy_thesis_card_panel`
- `ranking_trace_panel`
- `ranking_audit_report`
- `validated_strategy_candidate_reference_panel`

**Outputs**

- `ranked_strategy_execution_context_snapshot`
- `compatibility_projection_report`
- `phase8_strategy_ranking_handoff_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.

## P7.S8.M04 — `phase8_handoff_and_release_publisher`

Verify terminal candidate conservation, seal hashes and publish the technical phase release receipt.

**Source:** `src/quant_pipeline/phase_07_strategy_tournament/finalization/modules/P7_S8_M04_phase8_handoff_and_release_publisher.py`

**Inputs**

- `phase8_strategy_ranking_handoff_manifest`
- `ranked_strategy_candidate_panel`
- `final_blocked_candidate_panel`
- `abstained_candidate_panel`

**Outputs**

- `p7_phase_release_receipt`
- `p7_phase_release_manifest`

**Audit verdict:** implemented, covered by local and phase-level tests; production promotion remains disabled.
