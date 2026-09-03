# Arquitetura Integrada da P8

## Fluxo canônico

```text
P7 ranking + P6 shape + P5 beliefs + P2 market/account state
  → S1 Boundary / PIT snapshot
  → S2 Candidate context / dual book / ordinal preferences
  → S3 Scenario engineering
  → S4 Joint risk state
  → S5 Optimization / sizing / MPC
  → S6 Independent risk gate / hedge / lifecycle
  → S7 Orders / execution
  → S8 Stateful portfolio / accounting
  → S9 Runtime assurance / fallback / shadow
  → S10 Independent audit / P9 and P0 handoffs
```

## Camadas

### Contratos e foundation
Identidade, tempo, hashing, referências, eventos, razão e contexto. Nenhum algoritmo econômico deve ser duplicado aqui.

### Domínios de subfase
Cada subfase mantém seus modelos e serviços específicos, mas cruza fronteiras apenas por contratos públicos.

### Integration anti-corruption layer
`phase_08_portfolio_control.integration` traduz contratos entre os blocos históricos sem permitir payloads permissivos. Cada campo ausente que possua significado econômico gera erro ou capability explícita.

### Ports e adapters
Dados externos, broker, storage e solver entram por adapters. O domínio não faz I/O oculto.

## Decisões estruturais

- uma árvore física; não vários `PYTHONPATH`s encadeados;
- uma wheel; não cinco wheels que tentam compartilhar o mesmo namespace interno;
- `quant_pipeline` é namespace para coexistir com outras fases;
- `phase_08_portfolio_control` é regular para oferecer uma API consolidada;
- facades históricas permanecem privadas/compatíveis, não canônicas;
- arrays grandes continuam content-addressed em NPZ quando apropriado;
- registros pequenos e contracts usam Pydantic estrito;
- Decimal é usado em accounting; float/NumPy nos cálculos numéricos, com conversão explícita.

## Estados seguros

`NO_ACTION_VALID`, `NOT_SIZABLE`, `PORTFOLIO_INFEASIBLE`, `RISK_BLOCKED`, `CAPABILITY_UNAVAILABLE` e modos runtime conservadores são resultados normais. Integridade temporal, hash, lineage e accounting quebrados são erros fatais.
