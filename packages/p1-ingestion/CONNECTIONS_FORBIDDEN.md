# Conexões proibidas — Fase 1 — Ingestão e versionamento raw — V14.1 RC4.1

Este arquivo fecha explicitamente as conexões proibidas no nível da fase. A regra principal é: **toda conexão que não aparece em `CONNECTIONS_ALLOWED.md` é proibida por padrão**.

## Conexões permitidas, para referência

### Consome de
- `external_sources`
- `source_registry_config`
- `ingestion_run_config`

### Emite para
- `phase_02_quality_pit`

## Consumo proibido

A fase não pode consumir artefatos, estados, variáveis ou decisões vindos diretamente de:

- `phase_02_quality_pit`
- `phase_03_agents_rag_memory`
- `phase_04_feature_base`
- `phase_05_underlying_forecasts`
- `phase_06_candidate_generation`
- `phase_07_ranking`
- `phase_08_portfolio_backtest`
- `phase_09_audit_learning`
- `retro_agent`

## Emissão proibida

A fase não pode emitir artefatos, decisões, patches ou feedbacks diretamente para:

- `phase_03_agents_rag_memory`
- `phase_04_feature_base`
- `phase_05_underlying_forecasts`
- `phase_06_candidate_generation`
- `phase_07_ranking`
- `phase_08_portfolio_backtest`
- `phase_09_audit_learning`
- `retro_agent`

## Ações proibidas nesta fase

- limpar dados economicamente
- ajustar preços
- criar features
- criar target
- gerar previsão
- gerar candidato
- ranquear
- montar carteira

## Regras globais de bloqueio

- Proibido criar conexão fora de `CONNECTIONS_ALLOWED.md`.
- Proibido consumir output de fase futura.
- Proibido criar campo de target fora do contexto autorizado de treino.
- Proibido esconder input em variável global, cache implícito ou estado externo não contratado.
- Proibido alterar contrato global dentro do pacote da fase.
- Proibido emitir artefato oficial que não esteja em `OUTPUT_CONTRACTS.md`.
- Proibido consumir artefato oficial que não esteja em `INPUT_CONTRACTS.md` ou `optional_feedback_inputs`.
- Nenhum módulo pode consumir ou emitir artefato fora de `contracts/MODULE_IO_MATRIX.yaml`.

## Como interpretar feedback opcional

Entradas marcadas como opcionais, como `phase_09_audit_learning` ou `retro_agent_optional`, são válidas apenas quando existe ciclo anterior auditado. Elas nunca são obrigatórias no primeiro ciclo e nunca podem alterar o resultado de um backtest já fechado.
