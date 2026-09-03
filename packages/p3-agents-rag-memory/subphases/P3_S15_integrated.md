# P3.S15 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S15.

## 3. Dependências
P3.S15.M01, P3.S3.M01, P3.S4.M02, P3.S7.M01

## 4. Módulos
- `P3.S15.M01` — tool_registry_builder: Construir registry de ferramentas/adapters incluindo status real e PIT policy.
- `P3.S15.M02` — person_tool_entitlement_router: Conceder ferramentas plausíveis por papel, recursos, instituição e patch promovido.

## 6. Inputs
- `active_retro_policy_patch`
- `person_schema_policy`
- `person_seed_panel`
- `provider_adapter_registry_config`
- `tool_entitlement_config`
- `tool_registry`
- `tool_registry_config`

## 7. Outputs
- `person_tool_entitlement_panel`
- `tool_registry`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
