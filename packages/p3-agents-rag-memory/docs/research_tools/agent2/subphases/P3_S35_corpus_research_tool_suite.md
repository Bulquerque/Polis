# P3.S35 — Corpus Research Tool Suite

## Missão

Expor pesquisa explícita, point-in-time e auditável sobre o corpus congelado da P3, reutilizando S12/S20 e sem duplicar RAG.

## Módulos

- `P3.S35.M01` — carrega e verifica o snapshot do índice.
- `P3.S35.M02` — constrói políticas e budgets de recuperação.
- `P3.S35.M03` — registra handlers de documento, versão e proveniência.
- `P3.S35.M04` — registra handlers de contraprovas e timeline.
- `P3.S35.M05` — consolida e qualifica a família.

## Família pública

```text
research.corpus.v1
```

## Inputs principais

- `retrieval_index_manifest`;
- `phase3_run_snapshot`;
- artifact store injetado;
- metadata documental opcional;
- capability flags de versionamento/proveniência.

## Outputs

- snapshot e prontidão do corpus;
- política e budget;
- bundles de handlers;
- matriz operação × modo;
- readiness report.

## Não responsabilidades

- indexar novamente;
- consultar internet;
- gerar sinal ou decisão;
- selecionar modelo, feature, estratégia ou portfólio;
- alterar crenças diretamente;
- forçar consenso.

## Definition of Done

- código, schemas, contratos, configs, fixtures e documentação sincronizados;
- testes positivos, negativos, PIT e integração passando;
- manifestos de integridade válidos;
- sem processos de teste presos;
- promoção produtiva ainda dependente de P0/S40.
