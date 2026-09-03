# P3.S10 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S10.

## 3. Dependências
P3.S10.M01, P3.S7.M02, P3.S8.M02, P3.S9.M01

## 4. Módulos
- `P3.S10.M01` — warmup_scheduler: Ordenar eventos e heartbeats do warm-up usando o mesmo calendário do ciclo normal.
- `P3.S10.M02` — warmup_checkpoint_planner: Planejar checkpoints reproduzíveis e limites de replay.

## 6. Inputs
- `activation_config`
- `heartbeat_config`
- `validated_initial_social_graph`
- `validated_population_manifest`
- `validated_warmup_history`
- `warmup_checkpoint_config`
- `warmup_event_schedule`

## 7. Outputs
- `warmup_checkpoint_plan`
- `warmup_event_schedule`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
