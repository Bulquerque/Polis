# INPUT_CONTRACTS — phase_05_underlying_forecasts — RC4.1

## Required inputs
- `underlying_feature_matrix_raw`
- `underlying_feature_matrix_selected`
- `underlying_feature_factors_pca`
- `underlying_feature_embeddings`
- `feature_selection_report`
- `feature_lineage_report`
- `drift_safety_report`
- `phase5_feature_handoff_manifest`

## Optional feedback inputs
- `signal_feedback_report`

## Rules
- required_inputs_must_exist_for_first_cycle
- optional_feedback_only_when_previous_cycle_validated
- optional_feedback_absence_must_not_block_first_cycle
