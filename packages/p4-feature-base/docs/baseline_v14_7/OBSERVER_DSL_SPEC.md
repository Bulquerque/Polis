# Especificação da DSL de observadores

Exemplo:

```yaml
observer_id: momentum.price.vol_adjusted.63d
phenomenon_id: momentum
perspective_id: price_persistence
source_modalities: [underlying_market]
inputs: [adjusted_close]
operators:
  - return: {lookback: 63D}
  - realized_volatility: {lookback: 21D}
  - ratio: {}
  - lag: {periods: 1}
grain: [decision_time, entity_id]
horizon_group: medium
availability_policy: close_plus_source_latency
fit_policy: expanding_past_only
```

Toda receita deve declarar inputs, operadores, janela, lag, grain, disponibilidade, horizonte, rationale, failure modes, custo e lineage.
