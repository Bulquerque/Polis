# huber-irls-v1

- Resolver family: `ROBUST_LINEAR`
- Implementation: `builtin.huber_irls`
- Role: `CHALLENGER`
- Capability: `AVAILABLE`
- Minimum sample: `24`
- Compatible views: `TABULAR_INTERPRETABLE, SPARSE_MODALITY_AWARE`
- Target families: `RETURN, VOLATILITY, TAIL, PATH_RISK`

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
  "delta": 1.345,
  "max_iter": 40,
  "ridge": 0.0001
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
