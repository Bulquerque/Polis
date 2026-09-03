# P3.S22 — Belief Validation, Evidence & Commitment

## 1. Missão

Converter propostas estruturadas da S21 em atualizações válidas, evidências point-in-time e commitments pré-outcome.

## 2. Papel sistêmico

A subfase é a fronteira entre cognição e persistência. Ela não executa LLM, não recupera evidência nova, não atualiza o estado da pessoa e não avalia outcomes.

## 3. Dependências

- P3.S21.M06: `structured_belief_proposal_panel`;
- P3.S11.M03: `current_belief_state_panel`;
- P3.S2.M02: `phase3_run_snapshot`;
- P3.S4.M01: `proposition_registry_config`;
- P3.S20.M05, P3.S13.M02, P3.S12.M02 e P3.S21.M04 para evidências.

## 4. Módulos

- P3.S22.M01 — belief_state_validator;
- P3.S22.M02 — evidence_binding_validator;
- P3.S22.M03 — belief_outcome_commitment_logger.

## 5. Fluxo

```text
structured proposal
→ state validation
→ evidence binding
→ pre-outcome commitment
```

## 6. Inputs

Propostas tipadas, estado anterior, snapshot, proposition registry, retrieval evidence, GraphRAG evidence, RAG index e resultados de ferramenta já validados.

## 7. Outputs

- `validated_belief_update_panel`;
- `evidence_bound_belief_update_panel`;
- `belief_outcome_commitment_log`.

## 8. Contratos e invariantes

- nenhuma evidência futura;
- nenhum campo de trade ou outcome;
- support e opposition permanecem distintos;
- prior/new/delta são preservados;
- commitment acontece antes de maturity;
- hashes e ordenação são determinísticos;
- nenhuma dependência global oculta.

## 9. Compatibilidade

Os IDs, nomes de inputs, nomes de outputs e implementation targets originais são preservados. Os outputs fortes são projetados para subfases posteriores e P9 sem alterar contratos externos.

## 10. Falhas

Falha fechada para schema inválido, proposal futura, proposition/horizon inválidos, evidence ref ausente, evidence futura, colisão de IDs e commitment tardio.

## 11. Observabilidade

Todo registro preserva run/cycle/snapshot, producer, lineage, reason codes, coverage e status. A subfase não registra segredos nem payload bruto de ferramenta.

## 12. Testes

Especificação canônica: `tests/specifications/subphases/P3_S22_TEST_SPEC.yaml`.

A implementação adiciona testes unitários, contratuais, integrados, replay e lifecycle do instalador.

## 13. Definition of Done

Os três módulos estão implementados, schemas Draft 2020-12 validam, a vertical passa, replay é estável, apply/validate/idempotência/rollback passam e a produção continua bloqueada até qualificação P0.
