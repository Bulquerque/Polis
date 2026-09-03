# Release and Testing Guide

## Fast validation

```bash
python scripts/validate_release.py
python scripts/run_tests_bounded.py
```

The bounded runner disables third-party pytest plugin autoloading, limits numerical-library threads and runs the numerical integration and release-structure layers in separate subprocesses. This prevents numerical-library teardown from contaminating import/static checks.

## Manual test command

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
pytest -p force_exit_plugin -q tests/test_integrated_pipeline.py --durations=20 -p no:cacheprovider
```

## Build verification

```bash
python -m pip wheel . --no-deps --no-build-isolation -w /tmp/p4-wheel
```

Build products must remain outside the source tree.

## Qualification layers

1. Static structure and manifest validation.
2. Integrated S1→S9 regression.
3. Original subphase regression suites.
4. Clean wheel build and import test.
5. Cross-phase live qualification under P0 authority.

## Corrected release expectations

The deterministic full fixture materializes F01–F10. A representation-level warning may produce `DEGRADED_QUALITY` while retaining `completeness_status=COMPLETE`; any missing required family or blocking drift produces a blocked handoff.
