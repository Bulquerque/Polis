# Arquitetura das fronteiras externas

```text
P0–P8 wire formats
        │
        ▼
phase_09.compatibility
  ├── fingerprints.py
  ├── p0_reporting.py / p0_consumer.py
  ├── p3_boundary.py
  ├── legacy_feedback.py / legacy_consumers.py
  ├── p8_ingress.py
  ├── p8_feedback.py
  └── generated_schemas/
        │
        ▼
contratos canônicos da P9
        │
        ▼
S1 → S2 → ... → S10
```

## Isolamento

Os módulos científicos não importam P0–P8. A CI analisa a AST e rejeita qualquer import estático externo fora da camada de compatibilidade. Mesmo nessa camada, símbolos externos são descobertos dinamicamente ou executados em subprocesso.

## P8 ingress

1. valida os modelos públicos reais da P8;
2. exige `backtest_id` explícito;
3. reconcilia contexto e candidatos;
4. materializa os artefatos no store;
5. gera schemas, referências e receipts content-addressed;
6. constrói `P8_EVALUATION_HANDOFF_V1`;
7. executa o consumer S1 da P9 nos testes.

## Feedback de retorno

1. recebe feedback candidato da P9;
2. exige recomendação `PROMOTED`;
3. exige autorização da P0;
4. valida bounds e janela;
5. gera o union type exato da P8;
6. calcula o hash canônico pela própria biblioteca da P8;
7. prova aplicação e idempotência no loader real.

## P3

A fronteira de subprocesso é uma decisão de isolamento, não um workaround espalhado. Ela impede que o `quant_pipeline/__init__.py` regular da P3 esconda os namespace packages das demais fases.
