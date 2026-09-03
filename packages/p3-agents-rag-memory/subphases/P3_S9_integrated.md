# P3.S9 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S9.

## 3. Dependências
P3.S2.M02

## 4. Módulos
- `P3.S9.M01` — warmup_history_validator: Validar janela de warm-up estritamente anterior à avaliação e holdout.

## 6. Inputs
- `evaluation_window_config`
- `phase3_run_snapshot`
- `warmup_history_bundle`

## 7. Outputs
- `validated_warmup_history`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
