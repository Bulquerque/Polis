# Changelog

## 2.3.1rc3 — 2026-08-02

- added aggregate, regime/objective-slice and calibration-error LTR qualification gates;
- added a per-model runtime compatibility ledger;
- added confidence component coverage and explicit abstention reason codes;
- added canonical test-snapshot drift validation;
- added a governed non-empty ranking proof and P8 handoff proof;
- aligned native compatibility with P6 RC6.2 and bundle RC3;
- 336 tests passed; production promotion remains disabled.


## 2.3.0rc1 — 2026-08-02

- Added a fail-closed native P6 RC6.1 adapter at the S1 boundary.
- Added direct execution from a native P6 result through `run_phase7_from_p6_result(...)`.
- Validate original P6 artifact hashes and manifest references before normalization.
- Preserve P5 RC34 manifest provenance through the P6 market snapshot and compatibility report.
- Added structured calendar-day horizons instead of treating civil days as sessions.
- Added safe parsing for canonical decimal strings while rejecting non-finite and ambiguous values.
- Carry defined-risk and margin evidence from P6 qualification outputs or derive it only from reconciled bounded payoffs.
- Added explicit entry-cost and liquidity semantics without relabeling raw liquidity as a normalized score.
- Corrected conservation of candidates blocked before scoring.
- Added `EMPTY_VALID` closure for universes with zero eligible candidates.
- Removed ownership of the root `quant_pipeline` package to improve sibling-wheel coexistence.
- Aligned the NumPy requirement with P5 (`>=1.26,<3`).
- Added native P6, tamper, conservation, empty-valid, and public-entrypoint tests.
- Production promotion remains disabled.

## 2.2.0rc2 — 2026-08-02

- Reorganized P7 as one sequential S1-S8 phase with a single public namespace.
- Added `P7.S8.M04` as the dedicated phase release and P8 handoff authority.
- Corrected artifact temporal semantics and removed fabricated confidence defaults.
- Added structural quality gates and clean-release validation.
