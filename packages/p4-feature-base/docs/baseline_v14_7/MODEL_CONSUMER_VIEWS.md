# Views para consumidores da P5

A P4 não escolhe modelos, mas deve evitar que cada modelo reconstrua temporalidade, masks e lineage de forma diferente.

## Views oficiais

- `TABULAR_INTERPRETABLE`: matriz selecionada para modelos lineares, árvores e tabulares;
- `CROSS_SECTIONAL_RANKED`: ranks, neutralizações e universo por data;
- `SEQUENCE_MULTI_HORIZON`: tensores causais com idade da informação;
- `GRAPH_RELATIONAL`: nodes, edges, connectedness e estados de rede;
- `TAIL_RISK_SPECIALIST`: downside, jumps, cauda, opções e stress sistêmico;
- `REGIME_CONTEXT`: macro, sistema, regime e OOD contemporâneo;
- `LATENT_FAMILY`: PCA e encoder opcional por família;
- `SPARSE_MODALITY_AWARE`: blocos incompletos com masks e qualidade da fonte.

## Regra

Todos os views derivam dos mesmos artefatos canônicos e possuem hashes, grain, intervalo, lineage e política temporal. Nenhum view pode conter previsão, score ou target.
