# Integration Guide — P3.S39

## Inputs from Agent 1

P3.S39 expects these frozen contracts from S32–S34:

- `research_data_boundary_bundle`;
- `tool_operation_registry`;
- `research_mode_registry`;
- runtime `decision_time`, snapshots and entitlements.

Handlers consume P1/P2 data only through `PitResearchQueryPort`. They must not
open a P1 file, search directories or call live APIs.

## Outputs for P3.S40

```text
return_risk_volatility_handler_bundle
dependence_entropy_handler_bundle
event_window_scenario_handler_bundle
quant_tool_handler_bundle
quant_operation_mode_qualification
quant_qualification_evidence_package
```

S40 remains responsible for:

- registering handlers in the global registry;
- adapting requests from S21;
- mapping results and evidence into S21-compatible contracts;
- qualification and release integration;
- P4 supplemental candidate handoff and governance-deferred local P9 evidence.

## Handler factory

`QuantHandlerFactory` accepts one `PitResearchQueryPort` and returns seven
process-local handlers. Registration is explicit and has no import-time side
effect.

## Legacy alias

```text
quant.realized_volatility.v1
→ quant.diagnostics.v1 / realized_volatility
→ research_mode=BASIC
```

The alias must be resolved by S32/S40. P3.S39 does not create a second handler.

## Point-in-time rules

1. `decision_time` is injected by runtime.
2. Every external evidence record requires `available_at`.
3. `available_at > decision_time` is rejected.
4. Market records are sorted by `observation_time` after filtering.
5. Duplicate observation timestamps fail closed.
6. An event-window post-period must already be complete.
7. Cache and replay keys must include snapshots, method version and seed.

Qualification runs set `QuantCallContext.qualification_mode=true`. In that mode
`DATE_LEVEL_PIT_UNPROVEN`, `UNPROVEN` and snapshot-only records fail closed;
they are never promoted by the handler. Every market/event observation is also
required to satisfy `observation_time`/`event_time`/`observed_at <= decision_time`.

The event adapter is explicit and versioned as
`p3.s39.event-time-adapter.v1`: it preserves `event_time`, maps
`observed_at -> event_time` when present, and otherwise maps a valid
`reference_date` to the start of that daily date with
`event_time_precision=DAILY`. Missing or malformed temporal fields fail closed;
no current timestamp is manufactured.

M04 accepts a test report only when `status=PASS`, `executed>0`, `passed>0`,
`evidence_id`, `lineage_id`, a matching `evidence_hash`, and a matching
`report_hash` are present. Empty or status-only reports produce
`BLOCKED_UPSTREAM` qualification records.

## P4/P5/P9 compatibility

P3.S39 produces evidence and process metrics for later S40 projection. It does
not emit canonical P4 features. It does not call P5. P9 may evaluate operation
utility only after outcomes mature and only in N+1.

## Merge behavior

The patch is additive. Shared `extensions/__init__.py` files are byte-identical
to the S38 patch, so the installer may safely skip them when S38 is already
installed. Different existing files are never overwritten.
