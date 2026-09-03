# Agent 3 unified integration guide

## Order

1. Apply this additive patch to an extracted P3 RC4.1 package.
2. Build S38 and S39 handler bundles.
3. Convert bundles to S40 executable operations with `company_adapter` and `quant_adapter`.
4. Supply these operations through the `research_tool_operations` runtime service.
5. Run S40 preflight before S21 tool execution.
6. Use S40.M04 to extend the evidence map before S21.M04.

## Compatibility

- No implementation file from P3.S1–P3.S31 is overwritten.
- No direct P3→P5 connection is introduced.
- P4 remains an additive candidate handoff that is not wired. P9 evidence is
  local and `DEFERRED_BY_GOVERNANCE`; the RC4.1 global matrix forbids a direct
  P3→P9 connection.
- Backtest and replay keep network transports disabled.
- Unavailable company views remain `BLOCKED_UPSTREAM`.
