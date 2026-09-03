# P3.S11 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S11.

## 3. Dependências
P3.S10.M01, P3.S10.M02, P3.S11.M01, P3.S11.M02, P3.S3.M01, P3.S7.M01, P3.S8.M02, P3.S9.M01

## 4. Módulos
- `P3.S11.M01` — warmup_replay_orchestrator: Invocar repetidamente a pipeline canônica de ciclo em modo warm-up; nunca sintetizar estado diretamente.
- `P3.S11.M02` — bootstrap_leakage_guard: Validar que o estado de warm-up só contém eventos/outputs disponíveis antes da avaliação.
- `P3.S11.M03` — cycle_state_loader: Selecionar checkpoint inicial ou estado temporal N−1 e materializar o estado atual.

## 6. Inputs
- `active_retro_policy_patch`
- `canonical_cycle_pipeline_config`
- `initial_cycle_state_snapshot`
- `person_seed_panel`
- `prior_cycle_state_snapshot`
- `validated_initial_cycle_state_snapshot`
- `validated_initial_social_graph`
- `validated_warmup_history`
- `warmup_checkpoint_plan`
- `warmup_event_schedule`
- `warmup_replay_audit`
- `warmup_replay_config`

## 7. Outputs
- `current_belief_state_panel`
- `current_memory_state`
- `current_person_state_panel`
- `current_social_graph`
- `initial_cycle_state_snapshot`
- `validated_initial_cycle_state_snapshot`
- `warmup_replay_audit`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
