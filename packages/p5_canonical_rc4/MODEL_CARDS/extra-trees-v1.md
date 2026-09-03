# extra-trees-v1

- Resolver family: `TREE`
- Implementation: `builtin.extra_trees`
- Role: `CHALLENGER`
- Capability: `AVAILABLE`
- Minimum sample: `40`
- Compatible views: `TABULAR_INTERPRETABLE, CROSS_SECTIONAL_RANKED`
- Target families: `RETURN, DIRECTION, VOLATILITY, TAIL, PATH_RISK`

## Resource budget

```json
{
  "max_memory_mb": 512,
  "max_seconds": 30
}
```

## Parameters

```json
{
  "max_depth": 6,
  "min_samples_leaf": 3,
  "n_estimators": 20
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
