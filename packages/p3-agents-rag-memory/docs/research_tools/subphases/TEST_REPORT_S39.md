# P3.S39 Test and Qualification Report

## Result

`P3.S39 — Quantitative Diagnostic Tool Suite` passed the local S39 regression
and real-data qualification gates in the isolated integration tree. Legacy P3
regression is outside this disjoint S39 rerun.

| Gate | Result |
|---|---:|
| New S39 tests | 33/33 PASS |
| Real local qualification operations | 7/7 PASS |
| M04 operation/mode qualification matrix | 21/21 QUALIFIED_LOCAL |
| Existing P3 regression tests | NOT RUN IN THIS LANE |
| New Python compilation | PASS |
| Four module contracts | PASS |
| Sixteen generated schemas | PASS |
| Seven unique operations | PASS |
| Structural validator | PASS |
| Baseline file conflicts | 0 |
| S38 overlap conflicts | 0 |

## Test coverage

The new tests cover:

- return statistics and annualization;
- close-to-close, Parkinson and Garman–Klass volatility diagnostics;
- drawdown path and recovery state;
- Pearson and Spearman correlation, including ties and constant samples;
- Shannon and permutation entropy with frozen discretization policies;
- matured event windows and benchmark alignment;
- deterministic linear and quadratic scenario shocks;
- seeded bootstrap replay;
- non-finite output rejection;
- point-in-time invariance when future rows are added;
- random deterministic invariants;
- differential checks against NumPy and SciPy installed in the test environment;
- handler uniqueness, schemas, wrappers and qualification matrices.
- adversarial rejection of unproven PIT, future observations, missing artifact
  provenance, missing event time, and empty M04 evidence.
- real local P2 handoff replay without fixtures or external MCP.

NumPy and SciPy are test-only references. The runtime implementation uses the
Python standard library plus the Pydantic contract layer already used by P3.

## Legacy compatibility strategy

The baseline package freezes 81 canonical modules and 31 canonical subphases.
S39 therefore remains in an additive extension namespace:

```text
extensions/research_tools/
src/.../extensions/research_tools/modules/
contracts/research_tools/
```

It does not alter the legacy module matrix, schema registry, module directory or
subphase prompt directory. Global promotion belongs to P3.S40 after S32–S40 are
assembled. This preserves all 760 existing tests while retaining complete S39
contracts and integration overlays.

## Known unchanged baseline warning

Python 3.13 emits eight deprecation warnings in the existing multiprocessing
hardening test because the baseline uses `fork()` after threads have started.
The test passed. S39 itself creates no processes or threads.

## Tooling availability

`ruff` was not installed in the environment, so it was not downloaded or added as
a dependency. Compilation, AST-based structural checks, strict model tests,
property tests and the full regression suite were used instead.
