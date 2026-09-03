# kernel-ridge-v1

- Resolver family: `KERNEL`
- Implementation: `builtin.kernel_ridge_rbf`
- Role: `CHALLENGER`
- Capability: `AVAILABLE`
- Minimum sample: `24`
- Compatible views: `TABULAR_INTERPRETABLE`
- Target families: `RETURN, VOLATILITY`

## Resource budget

```json
{
  "max_memory_mb": 384,
  "max_seconds": 20
}
```

## Parameters

```json
{
  "alpha": 1.0,
  "gamma": 0.25,
  "max_dictionary": 128
}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
