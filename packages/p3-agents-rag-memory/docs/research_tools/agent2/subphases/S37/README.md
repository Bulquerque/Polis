# P3.S37 — Macro Observation Tool Suite

Extensão aditiva e point-in-time da Fase 3 para consulta macroeconômica descritiva.

## Estado

- `IMPLEMENTED_QUALIFIED_LOCAL`
- promoção produtiva: **não autorizada**
- composição final: depende de `P3.S40`
- autoridade de promoção: P0

## Família pública

`macro.observation.v1`

Operações:

- `search_series`
- `get_observations`
- `get_release_snapshot`
- `compare_series`
- `get_asset_context`

## Princípios

1. Nenhuma chamada de rede durante backtest.
2. `available_at <= decision_time` antes de busca, transformação ou comparação.
3. Valores revisados hoje não substituem o que era conhecido historicamente.
4. `VINTAGE_ANALYSIS` é bloqueado quando o upstream não preserva revisões reais.
5. A ferramenta descreve dados; não prevê, gera sinal, escolhe regime ou roda backtest.
6. Todos os resultados carregam cobertura, proveniência, prova PIT e hash determinístico.

Comece por `START_HERE.md`.
