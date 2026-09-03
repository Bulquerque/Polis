# P4 Feature Base — V14.9-RC1 Final Corrected

This package consolidates the implementations delivered independently for P4.S1–P4.S9 into one canonical source tree.

## Start here

1. Read `docs/01_ARCHITECTURE.md` to understand the nine-subphase pipeline.
2. Read `docs/02_INTEGRATION_GUIDE.md` before changing a boundary or artifact schema.
3. Read `docs/03_DEBUGGING_GUIDE.md` when tracing a failed run.
4. Read `docs/08_CROSS_PHASE_COMPATIBILITY.md` before merging into P0–P9.
5. Use `docs/09_FINAL_INTEGRATION_CHECKLIST.md` for the final monorepo handoff.
6. Run `python scripts/validate_release.py` for static release validation.
7. Run `python scripts/run_tests_bounded.py` for the bounded integrated S1→S9 regression suite.
8. During debugging, run one isolated layer with `python scripts/run_tests_bounded.py --layer integrated_pipeline`, `--layer v14_9_corrections` or `--layer release_structure`.

## Canonical execution entry point

```python
from quant_pipeline.phase_04_feature_base import ExecutionContext, run_integrated_phase

result = run_integrated_phase(inputs, context, encoder_requested=False)
```

The public entry point supports:

- snapshot runs, where records omit `decision_time` and inherit the run cutoff;
- historical backfills, where every record may carry its own `decision_time` and must satisfy `available_at <= decision_time <= run cutoff`;
- controlled partial completion when the history is too short for S7–S9;
- an optional encoder path that is never required for the primary PCA/selected-feature path.

## Release status

- 9 subphases
- 49 canonical modules
- unified source namespace
- reconciled S3→S4 and S6→S7 boundaries
- full raw-input S1→S9 regression
- P2/P3 legacy handoff compatibility retained
- all ten required economic families materialized in the full regression
- P5 handoff distinguishes COMPLETE, PARTIAL, DEGRADED and BLOCKED states
- conservative structural-selection and drift policies are mandatory

This is an integrated release candidate, not a production-promotion certificate. Live-provider scale, storage adapters and P0 global registration remain external qualification steps.
