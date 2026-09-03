# robust-ridge-v1

- Resolver family: `LINEAR`
- Implementation: `builtin.ridge`
- Role: `CORE`
- Capability: `AVAILABLE`
- Minimum sample: `24`
- Compatible views: `TABULAR_INTERPRETABLE, CROSS_SECTIONAL_RANKED, SPARSE_MODALITY_AWARE`
- Target families: `RETURN, DIRECTION, VOLATILITY, TAIL, PATH_RISK`

## Resource budget

```json
{
  "max_memory_mb": 256,
  "max_seconds": 10
}
```

## Parameters

```json
{
  "alpha": 1.0
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
