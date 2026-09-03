# foundation-prior-port-v1

- Resolver family: `FOUNDATION`
- Implementation: `optional.foundation_prior`
- Role: `SHADOW`
- Capability: `SKIPPED_CAPABILITY_UNAVAILABLE`
- Minimum sample: `128`
- Compatible views: `SEQUENCE_MULTI_HORIZON, LATENT_FAMILY`
- Target families: `RETURN`

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
