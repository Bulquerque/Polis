# Integration Guide

## Merge

O pacote é um overlay aditivo. Copie `src/`, `config/`, `contracts/`, `schemas/`, `subphases/` e documentação para a raiz do pacote P3, preservando os arquivos existentes.

Não substitua:

- registry dos 81 módulos originais;
- módulos `P3.S1–P3.S31`;
- modelos do S21;
- handoffs P4/P9 existentes.

Aplique:

- `contracts/MODULE_REGISTRY_OVERLAY.yaml` por merge aditivo;
- `config/CANONICAL_DAG_OVERLAY.yaml` no composition root da extensão;
- `config/CONFIG_BINDINGS.yaml` sem apagar bindings existentes.

## Dependências de entrada

S36 espera o `research_data_boundary_bundle` produzido futuramente por `P3.S33.M05`. Para qualificação local, `InMemoryPitMarketBoundary` fornece a mesma semântica usando artefatos congelados.

## Saída para S40

`P3.S36.M06` entrega:

- `market_tool_handler_bundle`;
- `options_tool_handler_bundle`;
- `market_derivatives_operation_mode_qualification`;
- `market_derivatives_tool_readiness_report`.

S40 registrará os handlers por `(tool_id, operation_id)` e construirá o gateway compatível com S21.

## Compatibilidade S21

O resultado completo é serializado em `ToolExecutionResponse.canonical_payload`. A ponte inicial usa `evidence_refs=()` porque o validador S21 existente aceita referências já recuperadas ou a referência sintética da própria execução. S40 preservará as evidências detalhadas dentro do envelope canônico.

## Operações bloqueadas

Uma operação ou modo com dados insuficientes deve permanecer `BLOCKED_UPSTREAM` e não entrar no entitlement efetivo. Não existe fallback que invente ajuste, IV, cadeia, calendário ou liquidez.
