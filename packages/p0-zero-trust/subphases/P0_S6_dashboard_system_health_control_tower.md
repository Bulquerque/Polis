# P0.S6 — Dashboard & System Health Control Tower

## Função

A P0.S6 é o quartel-general técnico da Fase 0. Consolida estrutura planejada, desenvolvimento, testes, saúde técnica, integridade Zero Trust, qualificação e prontidão de P0–P9 sem interferir automaticamente na execução das fases.

A subfase funciona durante todo o ciclo de desenvolvimento: fases ainda não iniciadas são representadas como `NOT_STARTED`, fases parciais como `IN_DEVELOPMENT` e falhas reais permanecem separadas de simples incompletude.

## Módulos

- **P0.S6.M01 — phase_dashboard_payload_collector**: normaliza telemetria, estados de desenvolvimento e qualificação. Aceita snapshots parciais e sintetiza fases planejadas ainda não iniciadas.
- **P0.S6.M02 — phase_health_panel_builder**: resolve os estados de fase, subfase e módulo nas dimensões documentação, desenvolvimento, testes, saúde, qualificação e prontidão.
- **P0.S6.M03 — global_control_tower_builder**: constrói a visão global, separando saúde do pipeline, saúde Zero Trust, integridade, alertas e readiness.
- **P0.S6.M04 — dashboard_exporter**: renderiza dashboard estática offline em HTML/CSS/JS/JSON, com hashes determinísticos e opção de materialização física.

## Estados principais

- Documentation: `INCOMPLETE | READY`
- Development: `NOT_STARTED | IN_DEVELOPMENT | IMPLEMENTED`
- Tests: `NOT_RUN | PARTIAL | PASS | FAIL`
- Health: `UNKNOWN | HEALTHY | WARNING | CRITICAL`
- Qualification: `NOT_ELIGIBLE | ELIGIBLE | RUNNING | FAILED | QUALIFIED`
- Readiness: `NOT_READY | READY`

`NOT_STARTED` e `IN_DEVELOPMENT` não são falhas técnicas. Eles tornam a fase `NOT_READY`, mas a causa permanece explicitamente distinguida de `CRITICAL`/`FAIL`.

## Fontes de estado

O payload de entrada `dashboard_phase_payload_all_phases` pode carregar, além de `phases`, snapshots opcionais e materializados:

- `registry_snapshot`
- `development_state_snapshot`
- `qualification_state_snapshot`

Essas fontes são normalizadas por M01 sem leitura oculta do filesystem, preservando replay e testabilidade.

## Dashboard

M04 gera quatro arquivos canônicos:

- `index.html`
- `assets/dashboard.css`
- `assets/dashboard.js`
- `data/control_tower.json`

A dashboard é offline, sem CDN e sem dependência de servidor. Quando `dashboard_output_dir` é fornecido no config, os arquivos são efetivamente escritos e seus hashes são registrados no `dashboard_export_manifest`.

## Não faz

Não processa dado econômico, não cria feature, não prevê, não ranqueia, não monta carteira, não altera backtest, não interrompe automaticamente outras fases e não chama agentes para corrigir problemas.
