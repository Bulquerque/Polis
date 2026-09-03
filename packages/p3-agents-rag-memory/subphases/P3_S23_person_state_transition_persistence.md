# P3.S23 — Person State Transition & Persistence

## 1. Missão
Materializar estados seguintes de pessoa e crença de forma determinística, gradual, versionada e auditável, e validar os candidatos sem recalcular ou reparar silenciosamente.

## 2. Escopo
S23 consome belief updates já validados e evidenciados pela S22. Ela atualiza somente conhecimento, atenção, confiança funcional e pressão de incerteza com regras explícitas. Trust, personalidade, capacidade cognitiva e proficiência de ferramentas permanecem inalterados sem evidência autoritativa.

## 3. Dependências
Upstream: `P3.S4.M02`, `P3.S11.M03`, `P3.S22.M02`. Dependência funcional obrigatória: S21 e S22 qualificadas localmente.

## 4. Módulos
1. `P3.S23.M01` — cria candidatos e o estado completo de crenças.
2. `P3.S23.M02` — aceita ou rejeita candidatos, sem recalcular.

## 5. Ordem de execução
`M01 → M02`. Os outputs de M01 são imutáveis; M02 não aplica clamp nem correção.

## 6. Inputs
M01 mantém exatamente os cinco inputs do IO matrix. M02 mantém exatamente os quatro inputs do IO matrix. Configuração e person policy são artefatos tipados, não estado global.

## 7. Outputs
- `next_person_state_panel`: candidatos com delta auditável.
- `next_belief_state_panel`: estado completo, incluindo crenças não alteradas.
- `validated_next_person_state_panel`: estados aceitos e rejeições materiais.

## 8. Limites de autoridade
A subfase não altera relações, memória, tool entitlements, população, personalidade estrutural ou contratos externos. Não produz targets, scores de seleção, pesos ou decisões de trade.

## 9. Invariantes e configuração
Slow e medium caps são escalados pelo tempo decorrido; fast cap é por ciclo. Todo delta registra prior, candidato, aceito, cap, razão, evidência e causa. `person_id`, `profile_hash`, life stage at creation e creator provenance são imutáveis. Belief refs são append-only.

## 10. Falhas
Duplicidades, pessoa inexistente, transição regressiva, família não declarada e schema inválido falham de forma tipada. M02 materializa rejeições e nunca produz um estado “corrigido”. Tool proficiency é preservada em M01 e qualquer mudança sem `executed_tool_call_refs` é rejeitada por M02.

## 11. Observabilidade
Lineage inclui os três inputs de estado da M01 e os dois artefatos da M02. Reason codes tornam caps, imutabilidade, versões e gaps contratuais auditáveis.

## 12. Testes
A especificação canônica permanece em `tests/specifications/subphases/P3_S23_TEST_SPEC.yaml`. A implementação adiciona unitários, contratos, integração, replay, schemas Draft 2020-12, wrappers, caps temporais, imutabilidade, tool proficiency, complete belief state e rollback do overlay.

## 13. Definition of Done
Código funcional, schemas gerados dos modelos, documentação alinhada, testes locais e integrados passando, apply/validate/idempotência/rollback verificados e status `QUALIFIED_LOCAL`. Produção continua bloqueada até P0 global.
