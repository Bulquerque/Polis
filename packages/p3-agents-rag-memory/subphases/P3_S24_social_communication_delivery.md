# P3.S24 — Social Communication & Delivery

## 1. Missão
Transformar intents sociais finais em mensagens declaradas, agendar eventos exclusivamente para N+1 e auditar a ligação entre comunicação, requests e entitlement sem afirmar execução não observada.

## 2. Escopo
A subfase possui três responsabilidades fechadas: roteamento, agendamento e auditoria request-level. Não atualiza confiança, relações ou memória.

## 3. Dependências
- Upstream: `P3.S11.M03`, `P3.S15.M02`, `P3.S21.M02`, `P3.S21.M05`, `P3.S23.M02`
- Downstream: `P3.S25.M01`, `P3.S25.M02`, `P3.S26.M01`, `P3.S26.M02`, `P3.S27.M03`

## 4. Módulos
1. `P3.S24.M01` — `social_message_router`
2. `P3.S24.M02` — `social_delivery_scheduler`
3. `P3.S24.M03` — `social_tool_usage_auditor`

## 5. Ordem de execução
`M01 → M02 → M03`.

## 6. Inputs
- `finalized_social_intent_panel`
- `current_social_graph`
- `validated_next_person_state_panel`
- `social_delivery_config`
- `social_message_panel`
- `social_delivery_panel`
- `validated_tool_call_request_panel`
- `person_tool_entitlement_panel`

## 7. Outputs
- `social_message_panel`
- `social_delivery_panel`
- `social_delivery_event_panel`
- `social_tool_audit_panel`

## 8. Limites de autoridade
- Nenhum efeito social no mesmo ciclo.
- Nenhum estado `SEEN`, `INTERPRETED` ou `USED` é produzido em N.
- Nenhuma execução de ferramenta é inferida por M03.
- Sem targets futuros, ranking, pesos ou sinais de trade.

## 9. Invariantes e configuração
PIT, lineage, produtor único, IDs determinísticos, idempotency keys, eventos N+1, preservação de undelivered e configuração versionada.

## 10. Falhas
Falhas de receptor, relacionamento, canal, orçamento, temporalidade, entitlement ou linkage são materiais. Não existe fallback silencioso.

## 11. Observabilidade
Registrar run/cycle/module IDs, message/delivery/event IDs, correlation/causation IDs, status, reason codes, contagens e latência calculada.

## 12. Testes
A especificação canônica permanece em `tests/specifications/subphases/P3_S24_TEST_SPEC.yaml`. A implementação acrescenta testes funcionais em `tests/phase_specific/` e no pacote standalone.

## 13. Definition of Done
- Três módulos funcionais com contratos originais preservados.
- Schemas gerados do código e validados como Draft 2020-12.
- Caminhos de N+1, undelivered, no-request, request rejeitado e entitlement incompatível testados.
- Integração S21–S24 e runner global fail-closed verificados.
- Nenhuma alegação de produção antes dos gates P0.
