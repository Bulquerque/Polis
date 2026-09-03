# P567 RC3 Compatibility Contract

**Adapter:** `P8.P567_RC3.BRIDGE`  
**Target release:** `0.3.0rc3`

## Required producer artifacts

### P5
- `phase5_output_handoff_manifest.embedded_v2_artifacts`
- market belief state
- return distributions
- forecast confidence
- regime/OOD states
- optional scenario, dependence, ambiguity and lineage sidecars

### P6
- canonical strategy candidates
- payoff, risk, cost/liquidity and qualification panels
- scenario valuation panel
- validated instruments
- strategy lineage

### P7
- complete P7 result, including foundation comparison outputs and finalization outputs
- comparison groups
- ranked, eligibility-blocked, safety-blocked and abstained populations
- ranking trace when ranked candidates exist

## Fail-closed conditions

- candidate absent from P6;
- duplicate terminal assignment;
- terminal population incomplete;
- comparison-group coverage incomplete;
- missing P6 payoff/cost/qualification;
- missing P5 predictive distribution;
- option instrument master absent;
- bridge publication after P8 decision;
- conflicting artifact IDs or bytes.

## Explicit adaptation policies

| Source | Native P8 decision |
|---|---|
| P7 cardinal/internal score | `ORDINAL`, no `score_value` |
| P7 confidence version only | `UNCALIBRATED` |
| P6 candidate ID | used as canonical ID with receipt disclosure |
| P6 strategy scale | unit-definition metadata |
| P6 lot/quantity increment absent | explicit one-candidate-unit bridge policy |
| P6 liquidity score | not converted to capacity units |
| P6 maximum loss | qualified only with proof flag |
| P6 option lifecycle not modelled | lifecycle unavailable |
| P5 `1D` | one calendar-day horizon |
| RC3 source hash | preserved as source metadata; P8 raw hash generated independently |
