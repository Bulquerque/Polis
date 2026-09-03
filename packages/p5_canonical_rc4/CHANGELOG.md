# Changelog

## 0.34.1rc4 — namespace compatibility hardening

- removed the regular `quant_pipeline/__init__.py` root so P5, P6 and P7 compose as an implicit namespace package;
- rebuilt the wheel for the P5/P6/P7 compatibility bundle;
- closed the prior-cycle feedback contract with strict schemas, content hashes, clocks and receipts;
- made the P5→P6 V2 handoff consumer-neutral and explicit about full/degraded mode;
- hardened S7 capability-vs-data errors, dimension-aware OOD and single-member disagreement handling;
- added live-current-P5 integration proof;
- production promotion remains disabled.

## 0.34.0 — RC34 Integration Hardened

- Added multistep block-bootstrap and copula scenario portfolios.
- Added OOS dependence champion selection and network consumption.
- Added threshold/HMM regime portfolio, multiple change detectors and disaggregated OOD.
- Added residual/cofailure ensemble evidence, non-negative stacking challenger and confidence components.
- Added empirical/stress ambiguity sets with data-derived radius.
- Added strong V2 marginal, scenario, dependence, regime/OOD, confidence and P6 manifest publication.
- Corrected V2 clocks to publish only artifacts available by their consumer decision time.
- Removed neutral defaults for missing confidence, OOD, change-point, jump and volatility evidence.
- Made previous-cycle feedback authority fail-closed.
- Separated P6-native capability from extended P5 scientific capability.
- Validated native belief records against P6 RC6.0-C and documented P7 as indirect via P6.
- Added fresh-process test certification and downstream compatibility tooling.
- Added Wave 4–7 qualification and adversarial tests.
- Preserved all 45 canonical module IDs and V1 projection.
