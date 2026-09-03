# histogram-boosting-v1

- Resolver family: `TREE`
- Implementation: `builtin.histogram_gradient_boosting`
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
  "learning_rate": 0.05,
  "max_iter": 25,
  "max_leaf_nodes": 15
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
