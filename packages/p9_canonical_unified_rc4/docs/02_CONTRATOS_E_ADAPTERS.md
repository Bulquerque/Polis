# Contratos e adapters

## Regra

Adapters existem apenas nas fronteiras onde as representações possuem semânticas diferentes. Eles traduzem campo a campo e falham quando a informação necessária não existe.

## S2 → S3

`adapt_trial_plan`:

- converte somente slots com configuração atribuída;
- ignora slots reservados até atribuição legítima;
- preserva configuração, fold, seed, fidelidade e orçamento;
- rejeita configuração desconhecida;
- não fabrica fold ou hash.

## S4 → S5

`build_s5_request`:

- exige métricas S4 qualificadas;
- exige séries, trades, folds e métricas pré-registradas explicitamente;
- não reconstrói séries a partir de Sharpe, CAGR ou outros resumos;
- garante coerência da configuração.

## S6 → S7

`project_stress_capacity`:

- projeta status de stress, distância de reverse stress e capacidade;
- preserva `None` quando capacidade não foi estimada;
- converte estados estruturalmente inseguros em hard blocks;
- não converte indisponibilidade em zero.

## S8 → S9

`build_promotion_evidence`:

- requer cards de configuração, gates, evidências e policies explícitas;
- verifica run e universo de configurações;
- preserva root causes fornecidas;
- não inventa score, confiança, causalidade ou aprovação.

## Nomes técnicos dos bundles

```text
P9_FOUNDATION_EXPERIMENT_BUNDLE_V1
P9_BACKTEST_METRICS_BUNDLE_V1
P9_ROBUSTNESS_STRESS_BUNDLE_V1
P9_PROSPECTIVE_ATTRIBUTION_BUNDLE_V1
```
