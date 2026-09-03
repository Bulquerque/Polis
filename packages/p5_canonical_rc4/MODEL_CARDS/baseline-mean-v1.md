# baseline-mean-v1

- Resolver family: `BASELINE`
- Implementation: `builtin.mean`
- Role: `RESERVE`
- Capability: `AVAILABLE`
- Minimum sample: `16`
- Compatible views: `TABULAR_INTERPRETABLE`
- Target families: `RETURN, DIRECTION, VOLATILITY, TAIL, PATH_RISK`

## Resource budget

```json
{
  "max_memory_mb": 128,
  "max_seconds": 5
}
```

## Parameters

```json
{}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
