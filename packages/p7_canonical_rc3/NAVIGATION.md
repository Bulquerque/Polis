# Navigation

## Start here

1. `README.md` — mission and public API.
2. `ARCHITECTURE.md` — sequential S1→S8 topology.
3. `SUBPHASES.md` — responsibility of each subphase.
4. `MODULE_CATALOG.md` — input/output contract for every module.
5. `contracts/MODULE_REGISTRY.yaml` — machine-readable module authority.
6. `DEBUGGING_RUNBOOK.md` — trace failures from P8 output back to P6 evidence.

## Source map

- `foundation/` — S1–S2 boundary, temporal safety, eligibility and grouping.
- `tournament/` — S3–S4 dominance, Pareto and interpretable scoring.
- `learning/` — S5–S6 offline ranker qualification and governed runtime scoring.
- `finalization/` — S7–S8 diversity, safety, abstention, ranking and P8 publication.
- `handoffs/` — explicit internal handoff assemblers. They normalize wire schemas only and may not invent economic facts.
- `runner.py` — public phase composition; no ranking mathematics.

## Finding ownership

Search a `module_id` in `contracts/MODULE_REGISTRY.yaml`. The entry gives the exact source path, inputs and outputs. Tests mirror the functional area under `tests/`.
