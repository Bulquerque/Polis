# P9.CL4 — Experiment Memory & Trial Ledger

## Missão
Inicializar e finalizar registros com resultados reais e contagem de tentativas.

## Autoridade
Esta subfase pertence à P9, não à P3.

## Módulos
- `P9.CL4.M01` — `research_budget_trial_ledger_manager`
- `P9.CL4.M02` — `retro_experiment_record_initializer`
- `P9.CL4.M03` — `retro_experiment_record_finalizer`

## Regras
- Holdout final cego.
- Uma mudança por experimento.
- Registro final inclui PROMOTED/REJECTED e métricas.
