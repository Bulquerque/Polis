# Changelog

## 0.3.0rc3 — 2026-08-04

### Compatibilidade P5–P7 RC3
- Adicionou bridge estrito `P8.P567_RC3.BRIDGE`.
- Materializou artefatos P5 RC3 como bundles P5 nativos e beliefs empíricos S3.
- Materializou painéis P6 RC3 como pacotes econômicos unitários P8.
- Materializou resultado completo P7 RC3 como ranking handoff P8 conservado.
- Separou os clocks de publicação P7 dos clocks da decisão consumidora P8.
- Preservou hashes reportados pela origem sem alegar equivalência com os bytes canônicos P8.
- Converteu scores P7 exclusivamente em semântica ordinal.
- Manteve confidence como uncalibrated quando não existe artefato content-addressed de calibração.
- Proibiu conversão de score de liquidez em capacidade de contratos.
- Bloqueou opções cujo exercise/assignment permanece `NOT_MODELLED`.
- Adicionou receipt de adaptação content-addressed.

### Qualificação
- Reexecutou a cadeia viva P5→P6→P7 e adaptou o resultado para P8.
- Adicionou golden path real all-abstained até S1/S2.
- Adicionou projeção contratual ranked até o universo estático S2.
- Adicionou regressões de conservação, economics ausente, clocks e lifecycle.

### Governança
- Produção permanece desabilitada.

## 0.2.0rc1 — 2026-08-04

- Corrigiu os bloqueadores semânticos e operacionais encontrados na RC0.
- Fechou PnL multi-horizonte, missing→zero, carteira completa S6, runtime safety, hard constraints, FX e open orders.
- Qualificou 624 testes e extração limpa.

## 0.1.0rc0 — 2026-08-04

- Consolidou as cinco implementações em uma árvore e wheel.
