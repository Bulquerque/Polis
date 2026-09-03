# P5 RC34 — Integration Hardened

Canonical CPU-first probabilistic market-belief and scenario engine.

- Package: `P5_INTEGRATED_RC34_INTEGRATION_HARDENED`
- Version: `0.34.1rc4.post2`
- Pipeline: `P5-RC34.1-CONTRACT-CLOSURE-RC4`
- Architecture: 9 subphases, 45 canonical modules, one registry, one runner
- Local tests: 127 passed, 0 failed
- Historical RC2 Coverage.py baseline: 86.14% (archived; not claimed for RC3)
- Statement coverage prior baseline: 90.40%
- True branch coverage prior baseline: 72.00%
- Production promotion: forbidden

## Implemented scope

- Wave 0: contract freeze, schemas and canonical registries.
- Wave 1: P4 boundary, filters, availability, lineage, calendar and fail-closed semantics.
- Wave 2: declarative targets, multifold walk-forward, sealed TEST, training and qualification.
- Wave 3: return, volatility, conditional-quantile, heavy-tail and EVT marginals.
- Wave 4: moving/stationary/regime bootstrap, empirical/Gaussian/t copulas, joint paths and dependence champion selection.
- Wave 5: regime/HMM, change points, disaggregated OOD, model disagreement, conformal calibration, ensemble evidence, confidence and ambiguity.
- Wave 6: strong V2 publication, V1 projection and content-addressed P5→P6 handoff.
- Wave 7: adversarial tests, bounded deterministic tests, clean package validation, wheel and release evidence.

## Honest limits

Ruff, mypy strict, Hypothesis and the Python 3.11/3.12/3.14 matrix were not executable in this host. Their configurations are present and their status is `NOT_EXECUTED_ENVIRONMENT_LIMITATION`. The live P5→P6→P7 source and wheel receipts pass; real P4/P8 repository integration and economic qualification remain external gates. These limitations do not permit production promotion.

## Commands

```bash
python -B tools/validate_package.py
python -B tools/run_isolated_tests.py
python -m pip wheel . --no-deps --no-build-isolation -w dist
```
