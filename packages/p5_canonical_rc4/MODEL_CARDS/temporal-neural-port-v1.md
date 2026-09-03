# temporal-neural-port-v1

- Resolver family: `TEMPORAL_NEURAL`
- Implementation: `optional.temporal_neural`
- Role: `SHADOW`
- Capability: `SKIPPED_CAPABILITY_UNAVAILABLE`
- Minimum sample: `128`
- Compatible views: `SEQUENCE_MULTI_HORIZON`
- Target families: `RETURN, VOLATILITY`

## Resource budget

```json
{
  "max_memory_mb": 2048,
  "max_seconds": 300
}
```

## Parameters

```json
{}
```

## Qualification policy

The resolver must produce multifold OOF evidence, compete against the target baseline and never consume sealed TEST for selection.
