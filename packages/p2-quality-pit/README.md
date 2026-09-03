# Fase 2 — Qualidade, Harmonização e Point-in-Time — Agent Package RC4.1

Versão: `V14.1-RC4.1`

## Função

Transformar artefatos brutos em painéis limpos e causalmente válidos, garantindo chaves, available_at, lineage e qualidade para Fases 3, 4 e 6.

## Entradas obrigatórias

- `handoff_manifest_to_phase_2`
- `source_registry`
- `raw_file_inventory`
- `source_snapshot_registry`
- `raw_readability_report`
- `raw_schema_hint_report`
- `ingestion_error_report`

## Feedback opcional de ciclos anteriores

- nenhum

## Outputs oficiais

- `clean_context_source_panel`
- `clean_document_panel`
- `clean_event_reference_panel`
- `source_quality_panel`
- `context_handoff_manifest`
- `clean_underlying_panel`
- `clean_macro_br_panel`
- `clean_macro_us_panel`
- `clean_benchmark_panel`
- `clean_calendar_panel`
- `clean_corporate_actions_panel`
- `quality_report_phase_2`
- `clean_option_quotes_panel`
- `clean_option_contract_panel`
- `clean_underlying_trade_panel`
- `clean_cost_reference_panel`
- `clean_liquidity_reference_panel`
- `phase3_handoff_manifest`
- `phase4_handoff_manifest`
- `phase6_handoff_manifest`


## Conexões permitidas

Consome de: `phase_01_ingestion`

Emite para: `phase_03_agents_rag_memory`, `phase_04_feature_base`, `phase_06_candidate_generation`

## Esta fase não faz

- features finais
- previsões
- candidatos de trade
- ranking
- carteira
- targets

## Como usar este pacote

O agente deve manter a implementacao executavel em `src/`, mas nao pode alterar contratos em `contracts/`, `schemas/` ou `modules/` sem atualizar o pacote global.

## Estado desta entrega integrada

A superfície pública RC4.1 foi preservada, mas a implementação em `src/` foi endurecida e integrada.
O `qualification/MASTER_PHASE_TEST_SPEC.yaml` permanece como especificação histórica de pré-implementação e não deve ser usado isoladamente para inferir o estado técnico desta entrega.

Antes de integrar, leia **`INTEGRATION_AND_CORRECTION_GUIDE.md`**, que descreve:

- correções aplicadas módulo a módulo;
- profile estrito de produção;
- passos de substituição;
- correções/verificações ainda necessárias fora da P2;
- problema preexistente de manifesto da P0;
- gates obrigatórios após integração.
