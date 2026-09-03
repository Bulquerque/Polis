# P3.S16 — Integrated subphase

## 1. Missão
Implementar e integrar as responsabilidades canônicas de P3.S16.

## 3. Dependências
P3.S15.M01, P3.S15.M02, P3.S16.M01

## 4. Módulos
- `P3.S16.M01` — mcp_tool_gateway_policy_builder: Definir permissões, PIT, budget, cache/freeze, credenciais indiretas e provenance.
- `P3.S16.M02` — tool_call_audit_contract_builder: Definir envelope e eventos obrigatórios para execução real de ferramentas.

## 6. Inputs
- `mcp_gateway_policy`
- `person_tool_entitlement_panel`
- `provider_adapter_registry_config`
- `tool_gateway_config`
- `tool_registry`

## 7. Outputs
- `mcp_gateway_policy`
- `tool_call_audit_contract`

## 10. Falhas
- Falhar de forma explícita em schema, temporalidade, lineage ou dependência não declarada.

## 12. Testes
- Unitários por módulo, integração da subfase e contratos de fronteira.

## 13. Definition of Done
- Contratos, implementação, schemas, testes, documentação e observabilidade alinhados.
