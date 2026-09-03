# P9.CL5 — Promotion & N+1 Handoff

## Missão
Verificar evidência, decidir promoção e emitir patch para N+1.

## Autoridade
Esta subfase pertence à P9, não à P3.

## Módulos
- `P9.CL5.M01` — `promotion_evidence_completeness_guard`
- `P9.CL5.M02` — `retro_candidate_promotion_gate`
- `P9.CL5.M03` — `next_cycle_retro_handoff_builder`

## Regras
- Holdout final cego.
- Uma mudança por experimento.
- Registro final inclui PROMOTED/REJECTED e métricas.
