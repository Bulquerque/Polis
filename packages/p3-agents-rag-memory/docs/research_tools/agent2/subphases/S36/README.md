# P3.S36 — Market & Derivatives Observation Tool Suite

Overlay aditivo para a Fase 3, implementando observação histórica de mercado e derivados sem modificar `P3.S1–P3.S31`.

## Famílias e operações

### `market.observation.v1`

- `get_snapshot`
- `get_history`
- `get_liquidity`
- `get_corporate_actions`
- `compare_instruments`

### `options.observation.v1`

- `get_contracts`
- `get_chain_snapshot`
- `get_quote_history`
- `get_surface_diagnostics`

## Princípios

- somente leitura;
- `available_at <= decision_time`;
- contratos de opção visíveis por `first_seen_date`;
- sem rede em backtest;
- sem sinal, ranking, estratégia ou portfólio;
- preço histórico B3 tratado como bruto por padrão;
- ajustes não são fabricados;
- diagnóstico de superfície usa IV observada;
- nenhum solver de IV ou interpolação é executado silenciosamente;
- operações avançadas são bloqueadas quando o upstream não fornece os dados.

## Execução local segura

```bash
python tools/run_tests_safely.py \
  --p3-base-src /caminho/para/phase_03/src \
  --timeout 60
```

O script executa compilação e grupos de testes sequencialmente, com timeout individual e sem multiprocessing.
