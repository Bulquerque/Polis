# P3.S40 Test Report

## Result

P3.S40 passed all focused, compatibility and legacy regression blocks executed in the isolated environment.

| Suite | Passed |
|---|---:|
| S40 focused runtime/evidence/contracts | 17 |
| S39 compatibility | 28 |
| Existing P3 baseline | 760 |
| Total across disjoint suites | 805 |

## Baseline blocks

The 760 legacy tests were executed in bounded commands: contracts, foundation, runtime context, runtime engine, hardening, products, society, integration, final integration, phase-specific, scientific evaluation and top-level tests. The release-manifest test was executed in a separate qualification copy after regenerating manifests; the delivered additive patch intentionally does not overwrite canonical release metadata.

## Additional gates

- Python compilation: PASS
- Eight module contracts: PASS
- 31 Draft 2020-12 schemas: PASS
- Structural validator: PASS
- Pre-existing-file integrity: PASS
- No network imports in S40 runtime: PASS
- Actual S39 handler through S40 gateway: PASS
- Actual S21.M03 and S21.M04 bridge: PASS
- Future evidence rejection: PASS
- Deterministic PIT proof hashing: PASS
- Alias dispatch without second handler: PASS
- P4/P9 honest unwired-consumer status: PASS

## Warnings

The existing runtime-hardening suite emitted eight Python 3.13 warnings about `fork()` after threads. This behavior belongs to legacy tests and was not introduced by S40. Ruff and mypy were not installed in the environment; no package installation was performed.
