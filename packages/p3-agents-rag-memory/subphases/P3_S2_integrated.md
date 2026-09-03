# P3.S2 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S2.

## 3. Dependências
P3.S1.M02, P3.S2.M01, P3.S2.M02

## 4. Módulos
- `P3.S2.M01` — point_in_time_context_gate: Aplicar o firewall available_at<=as_of_time e distinguir tempos de evento, eficácia e disponibilidade.
- `P3.S2.M02` — phase3_run_snapshot_builder: Congelar inputs, configs, schemas, adapters, seeds e hashes da execução.
- `P3.S2.M03` — model_knowledge_cutoff_firewall: Classificar risco de conhecimento incorporado nos pesos e falhar fechado em gates qualificatórios.

## 6. Inputs
- `config_bindings_registry`
- `evaluation_protocol_config`
- `evaluation_window_config`
- `model_knowledge_cutoff_policy_config`
- `p3_schema_authority_inventory`
- `phase3_handoff_manifest`
- `phase3_run_snapshot`
- `pit_validated_context`
- `provider_adapter_registry_config`
- `validated_context_inputs`

## 7. Outputs
- `model_knowledge_cutoff_report`
- `phase3_run_snapshot`
- `pit_validated_context`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
