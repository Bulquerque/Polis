# P7 Strategy Tournament — 2.3.1rc3

P7 is a single sequential phase that converts validated strategy candidates from P6 into an auditable ranking handoff for P8.

## Execution flow

```text
P5 belief provenance
  -> P6 strategy synthesis RC6.2
  -> S1 native/canonical boundary and temporal integrity
  -> S2 eligibility and comparability
  -> S3 dominance, Pareto and factor adjustment
  -> S4 interpretable scoring
  -> S5 offline LTR training and qualification
  -> S6 runtime scoring, calibration and hybrid blend
  -> S7 similarity, diversity, safety and abstention
  -> S8 deterministic ranking and P8 publication
```

The offline S5 path is separately callable and cannot train during runtime. Runtime defaults to `INTERPRETABLE_ONLY` until a governed LTR model is supplied.

## Public API

- `run_foundation_from_p6(...)`
- `run_runtime_from_foundation(...)`
- `run_phase7(...)`
- `run_phase7_from_p6_result(...)`
- `run_offline_ltr(...)`

`run_phase7_from_p6_result(...)` accepts the native result returned by P6 RC6.2. The S1 adapter validates original P6 hashes before normalization and preserves P5 RC34 provenance through the P6 snapshot.

## Compatibility behavior

- canonical P7 handoffs remain supported;
- native P6 RC6.2 manifests and Pydantic artifacts are supported;
- calendar-day horizons are explicit and are not silently converted to sessions;
- numeric strings are parsed only under declared numeric semantics;
- missing liquidity, margin confidence, calendar, OOD, or score confidence stays unavailable;
- candidates blocked before scoring remain conserved as eligibility-blocked;
- an all-blocked universe closes as `EMPTY_VALID` rather than failing downstream.

## Engineering properties

- one installable package and one public namespace;
- 8 subphases and 33 registered modules;
- one canonical representation after S1;
- content-addressed artifacts and explicit transition manifests;
- fail-closed temporal, safety, and contract validation;
- candidate conservation through terminal states;
- deterministic ranking and replay;
- explicit abstention when evidence is unavailable;
- no portfolio weights, trade execution, or same-cycle learning in P7.

See `COMPATIBILITY.md`, `NAVIGATION.md`, `ARCHITECTURE.md`, `MODULE_CATALOG.md`, `DEBUGGING_RUNBOOK.md`, and `reports/`.

Production promotion remains disabled until economic and prospective qualification are completed.

## Offline wheel build

```bash
python -m pip wheel . --no-deps --no-build-isolation -w dist
```
