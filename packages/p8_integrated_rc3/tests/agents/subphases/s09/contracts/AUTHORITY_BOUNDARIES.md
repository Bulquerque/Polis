# Authority boundaries

## Inputs

- Immutable monitoring baselines and scenario/risk references from S3/S4.
- Champion/challenger decision references and pre-qualified fallbacks from S5/S6.
- Stateful evidence, orders, fills, positions and accounting snapshots from S7/S8.
- Promoted policy bounds from P9, authorized by P0 and effective only in later cycles.

## Outputs

- `P8_RUNTIME_CONTROL_COMMAND_V1` to S7/S8/orchestrator.
- Conservative `P8_RUNTIME_ADAPTATION_V1` records.
- Runtime/shadow evidence consumed by S10 and P9.

## Forbidden authority

S9 cannot send broker orders, mutate ledgers, promote policies, retrain models, alter P5–P7 artifacts or increase risk appetite.
