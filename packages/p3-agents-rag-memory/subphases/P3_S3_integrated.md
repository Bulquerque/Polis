# P3.S3 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S3.

## 3. Dependências
P3.S2.M02

## 4. Módulos
- `P3.S3.M01` — promoted_retro_update_ingestor: Validar e ativar apenas patch de prompt/tool/retrieval já promovido pela P9 para N+1.
- `P3.S3.M02` — matured_belief_feedback_ingestor: Ingerir feedback P9 de crenças maturadas e disponibilizá-lo apenas como experiência N+1.

## 6. Inputs
- `p9_belief_outcome_feedback_package`
- `phase3_learning_feedback_handoff_manifest`
- `phase3_retro_handoff_manifest`
- `phase3_run_snapshot`
- `retro_memory_update_package`
- `retro_patch_compatibility_config`

## 7. Outputs
- `active_belief_feedback_bundle`
- `active_retro_policy_patch`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
