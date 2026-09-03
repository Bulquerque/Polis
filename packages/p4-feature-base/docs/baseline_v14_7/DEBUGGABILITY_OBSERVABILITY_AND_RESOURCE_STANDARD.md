# Padrão de debugabilidade e observabilidade

## Objetivo

Um erro precisa ser localizável por `run_id`, `cycle_id`, `module_id`, `artifact_id` e `lineage_id` sem abrir grandes payloads.

## Eventos mínimos

Cada módulo emite:
1. `module_started`;
2. `input_contract_validated`;
3. eventos específicos de fit ou cálculo;
4. `artifact_emitted`;
5. `module_succeeded`, `module_failed` ou `module_skipped`.

## Logging

- JSON estruturado;
- sem secrets, textos integrais ou frames enormes;
- erro contém código estável e contexto seguro;
- warnings são agregados por tipo;
- logs não são usados como contrato de dados.

## Diagnóstico determinístico

Todo failure report inclui:
- versão dos contratos;
- snapshot dos inputs por hash;
- config efetiva;
- seed;
- último módulo concluído;
- artefatos produzidos;
- causa original preservada.

## Recursos

Cada módulo declara orçamento de:
- tempo;
- memória;
- linhas por batch;
- número máximo de grupos;
- comportamento em degradação.

Nenhum módulo pode ficar rodando indefinidamente. Operações iterativas têm `max_iterations`, timeout cooperativo e progresso observável.
