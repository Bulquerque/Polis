# P3.S35 — Corpus Research Tool Suite

Implementação completa da primeira subfase do Agente 2 da extensão de ferramentas de pesquisa da Fase 3.

## Escopo

A subfase expõe a família canônica `research.corpus.v1` com seis operações:

- `search`
- `get_document`
- `compare_versions`
- `find_counterevidence`
- `build_timeline`
- `inspect_provenance`

Ela reutiliza os artefatos e índices congelados de `P3.S12` e não cria um segundo RAG. A integração com a cognição ocorre posteriormente pelo `ToolGatewayPort` de `P3.S40`.

## Garantias principais

- filtro point-in-time antes da recuperação e do reranking;
- nenhuma rede obrigatória em backtest;
- baseline lexical BM25 determinístico;
- recuperação densa e reranking apenas por portas opcionais e snapshot-pinned;
- RRF para fusão de rankings quando recuperação semântica estiver disponível;
- proveniência P1→P2→P3 preservada quando o boundary correspondente estiver disponível;
- fallback de bytes brutos para conteúdo indexado sempre explícito e marcado como `DEGRADED`;
- aliases legados resolvidos sem segundo handler;
- contratos Pydantic estritos e JSON Schemas gerados.

## Dependência de integração

Este ZIP é um overlay para o pacote canônico da P3 RC4.1. Ele depende dos contratos e componentes existentes em:

```text
quant_pipeline.phase_03_agents_rag_memory
```

Consulte `INTEGRATION_GUIDE.md` antes de copiar os arquivos.

## Validação segura

```bash
python tools/validate_package.py --p3-base-src /caminho/para/P3/src
python tools/run_tests_safely.py --p3-base-src /caminho/para/P3/src
```

Os testes são executados em grupos com timeout e sem paralelismo para evitar processos presos.
