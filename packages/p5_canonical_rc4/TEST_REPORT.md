# Test report — RC34 Integration Hardened

- Collected: 121
- Executed in a fresh subprocess per test file: 121
- Passed: 121
- Failed: 0
- Python executed: 3.13.5
- External test tooling unavailable: Ruff, mypy strict, Hypothesis

The suite covers contracts, source limits, P4 boundary, target/split semantics, marginal models, scenario generation, copulas, dependence, regime/OOD, calibration/ensemble, V2 publication, fail-closed behavior and deterministic content. Fresh-process execution prevents numerical-runtime accumulation from making results order-dependent.
