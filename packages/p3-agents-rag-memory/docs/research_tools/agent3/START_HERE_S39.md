# START HERE — P3.S39 Quantitative Diagnostic Tool Suite

This additive patch introduces `P3.S39` without changing implementations from
`P3.S1` through `P3.S31`.

## Canonical modules

- `P3.S39.M01 return_risk_volatility_handler_bundle_builder`
- `P3.S39.M02 dependence_entropy_handler_bundle_builder`
- `P3.S39.M03 event_window_scenario_handler_bundle_builder`
- `P3.S39.M04 quant_tool_bundle_method_qualification_builder`

## Safety boundary

The suite is descriptive. It does not run backtests, select features or models,
generate signals, optimize portfolios, query P5, assign scenario probability or
choose the best historical window.

## Point-in-time boundary

All records must contain `available_at`. Handlers reject records whose
`available_at` exceeds the runtime `decision_time`. Event windows are rejected
until the complete requested post-event window is observable.

## Installation

Use the included `APPLY_PATCH.py` against an extracted P3 package. Run without
`--apply` first. The installer refuses to overwrite a different existing file.
