# kalman-dlm-v1

- Resolver family: `STATE_SPACE`
- Implementation: `builtin.kalman_dlm`
- Role: `CHALLENGER`
- Capability: `AVAILABLE`
- Minimum sample: `32`
- Compatible views: `TABULAR_INTERPRETABLE`
- Target families: `RETURN, VOLATILITY`

## Resource budget

```json
{
  "max_memory_mb": 256,
  "max_seconds": 15
}
```

## Parameters

```json
{
  "observation_scale": 0.001,
  "process_scale": 0.0001,
  "ridge": 1.0
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
