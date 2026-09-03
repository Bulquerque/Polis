# P3.S1 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S1.

## 3. Dependências
P3.S1.M01

## 4. Módulos
- `P3.S1.M01` — phase2_handoff_contract_validator: Validar presença, schema, versão, hashes e cardinalidade do handoff da P2.
- `P3.S1.M02` — source_quality_context_guard: Aplicar a política canônica de qualidade recebida da P2 sem recalcular qualidade.

## 6. Inputs
- `clean_context_source_panel`
- `clean_document_panel`
- `clean_event_reference_panel`
- `context_handoff_manifest`
- `phase3_handoff_manifest`
- `source_quality_panel`
- `source_quality_policy_config`
- `validated_phase2_handoff`

## 7. Outputs
- `validated_context_inputs`
- `validated_phase2_handoff`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
