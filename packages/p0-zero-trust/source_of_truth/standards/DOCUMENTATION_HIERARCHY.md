# Documentation Hierarchy — V14.1 RC4.1

## Nível global

Documentos transversais vivem normativamente no master global `global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/source_of_truth/`. A árvore da Fase 0 contém somente um espelho derivado de compatibilidade para portabilidade e testes locais; ela não é autoridade normativa.

## Nível da fase

Cada fase mantém apenas documentação específica:

- `README.md`
- `PHASE_OVERVIEW.md`
- `PHASE_FUNCTION.md`
- `INPUT_CONTRACTS.md`
- `OUTPUT_CONTRACTS.md`
- `MODULE_CATALOG.md`
- `SUBPHASES.md`
- `DIAGRAM_INTERPRETATION.md`
- `AGENT_PROMPT.md`
- `SOURCE_OF_TRUTH.md`

## Nível do módulo

Módulos ficam em YAML curto, com função, inputs, outputs, validações, fail-fast e conexões.

Contratos derivados obrigatórios presentes em cada pacote de fase:

- `CONNECTIONS_ALLOWED.md`
- `CONNECTIONS_FORBIDDEN.md`
- `INTERNAL_CONTRACTS.md`
- `MODULE_BREAKDOWN.md`

## Documentos adicionais

`CHANGELOG.md`, `GLOBAL_CONTEXT.md`, `REPORT_ALIGNMENT.md`, `PHASE0_REPORTING.md`, `PHASE_FORBIDDEN_ACTIONS.md` e padrões locais são addenda. Eles não substituem os documentos canônicos acima.
