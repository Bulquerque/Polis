# Mapeamento RC4.1 → V14.6-RC1

| Módulo RC4.1 | Responsabilidade nova |
|---|---|
| P4.S1.M01 phase2_feature_intake_validator | P4.S1.M01 + P4.S1.M03 + P4.S2.M01–M04 |
| P4.S1.M02 phase3_social_feature_intake_validator | P4.S1.M02 + P4.S1.M03 + P4.S4.M07 |
| P4.S1.M03 feature_bus_builder | P4.S2.M04 canonical_observation_store_builder |
| P4.S2.M01 price_liquidity_features | P4.S4.M01, P4.S4.M02 e P4.S5.M04 |
| P4.S2.M02 momentum_trend_features | P4.S5.M01 |
| P4.S2.M03 reversion_pair_cluster_features | P4.S4.M04, P4.S5.M02 e P4.S5.M05 |
| P4.S2.M04 historical_risk_tail_features | P4.S4.M03 e P4.S5.M03 |
| P4.S2.M05 correlation_entropy_structure_features | P4.S4.M04 e P4.S5.M05 |
| P4.S2.M06 macro_regime_social_features | P4.S4.M06, P4.S4.M07, P4.S5.M06 e P4.S5.M08 |
| P4.S2.M07 feature_family_assembler | P4.S6.M01, P4.S6.M02 e P4.S6.M04 |
| P4.S3.M01 transform_normalization_interactions | P4.S6.M03, P4.S7.M01 e P4.S7.M02 |
| P4.S4.M01 feature_selection_builder | P4.S7.M03 e P4.S7.M04 |
| P4.S4.M02 feature_factor_pca_builder | P4.S8.M01 |
| P4.S4.M03 feature_embedding_builder | P4.S8.M02 e P4.S8.M03 |
| P4.S5.M01 feature_lineage_drift_quality_gate | P4.S9.M01 e P4.S9.M02 |
| P4.S5.M02 phase5_feature_handoff_builder | P4.S9.M03 e P4.S9.M04 |

## Política

Os IDs antigos ficam congelados na referência RC4.1. A implementação nova utiliza IDs novos e adaptadores temporários apenas para os oito outputs externos.
