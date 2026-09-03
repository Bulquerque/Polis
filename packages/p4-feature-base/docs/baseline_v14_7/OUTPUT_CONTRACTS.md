# Outputs da P4 V14.6-RC1

## Legados obrigatórios

- `underlying_feature_matrix_raw` (alias de `underlying_feature_matrix_interpretable`);
- `underlying_feature_matrix_selected`;
- `underlying_feature_factors_pca`;
- `underlying_feature_embeddings` — pode estar desativado/ausente conforme qualidade, sem bloquear P5;
- `feature_selection_report`;
- `feature_lineage_report`;
- `drift_safety_report`;
- `phase5_feature_handoff_manifest`.

## Suplementares

- `feature_observer_registry`;
- `feature_parameter_policy_registry`;
- `perspective_conflict_panel`;
- `feature_transform_state_manifest`;
- `representation_fold_plan`;
- `representation_quality_report`;
- `encoder_hyperparameter_search_report`;
- `horizon_feature_set_manifest`;
- `model_consumer_view_manifest`;
- `p4_to_p5_integration_receipt`.

Nenhum output contém label, previsão, candidato, ranking, peso ou P&L.
