# Fase 1 — Ingestão, Inventário e Versionamento — Agent Package RC4.1

Versão: `V14.1-RC4.1`

## Função

Capturar, versionar e registrar fontes brutas imutáveis, criando manifesto de handoff para a Fase 2 sem limpar ou modelar dados.

## Entradas obrigatórias

- `source_registry_config`
- `ingestion_run_config`
- `source_credentials_handle`
- `source_calendar_config`
- `local_raw_file_paths`
- `api_source_definitions`
- `manual_source_definitions`

## Feedback opcional de ciclos anteriores

- nenhum

## Outputs oficiais

- `handoff_manifest_to_phase_2`
- `source_registry`
- `raw_file_inventory`
- `source_snapshot_registry`
- `raw_readability_report`
- `raw_schema_hint_report`
- `ingestion_error_report`

## Conexões permitidas

Consome de: `external_sources`

Emite para: `phase_02_quality_pit`

## Esta fase não faz

- limpeza econômica
- harmonização de tickers
- features
- previsões
- candidatos
- ranking
- backtest
- targets

## Como usar este pacote

O agente deve manter a implementacao executavel em `src/`, mas nao pode alterar contratos em `contracts/`, `schemas/` ou `modules/` sem atualizar o pacote global.