# Arquitetura unificada

```text
P1/P2 snapshots
    ↓
P3.S33 boundary (contrato externo do Agente 1)
    ├── S35 corpus
    ├── S36 market/options
    └── S37 macro
          ↓
handler bundles imutáveis
          ↓
P3.S40 registry/gateway/evidence
          ↓
S21 cognição → P4/P9
```

As famílias não se importam mutuamente. Elas compartilham somente contratos e portas congelados. S35 reutiliza S12/S20; S36 não cria sinais ou candidatos; S37 não chama APIs live em backtest.
