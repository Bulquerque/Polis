# Ondas de implementação — V14.6-RC1

## Onda 0 — Contratos e registries

Congelar os 49 módulos, dez famílias, observers CORE, parâmetros, schemas e handoffs.

## Onda 1 — S1–S3

Autoridade de fronteira, tempo, missingness, canonical store, DSL e operadores. Nenhum módulo econômico começa antes desses contratos.

## Onda 2 — S4 CORE

Implementar preço, liquidez, risco realizado, cross-asset, opções, macro/eventos, social e fundamentos com oracles independentes.

## Onda 3 — S5 CORE

Implementar somente as 32 hipóteses fundamentais pré-registradas. Extensões e experimentais permanecem desligadas por feature flags contratuais até um ciclo N+1 aprovado.

## Onda 4 — S6–S7

Alignment, conflito, interações registradas, horizontes, transforms, neutralização e seleção estrutural.

## Onda 5 — S8 Tier 0/1

Gerar folds, matriz interpretável e PCA/Sparse PCA. P5 já deve conseguir consumir esta versão.

## Onda 6 — S8 Tier 2

Implementar o encoder challenger apenas se `encoder_execution_decision=AUTHORIZED`, comparando exatamente as 2 configurações pré-registradas. Falha, ausência ou baixa qualidade do encoder não bloqueia a matriz interpretável nem o Sparse PCA.

## Onda 7 — S9/P5/P0

Lineage, drift, consumer views, handoff, receipt e qualificação cruzada.
