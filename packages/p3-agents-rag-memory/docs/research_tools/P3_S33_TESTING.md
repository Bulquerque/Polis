# P3.S33 Testing and Qualification

## Suítes específicas

```text
test_p3_s33_m01_views.py
test_p3_s33_m02_custody.py
test_p3_s33_m03_temporal.py
test_p3_s33_m04_entity_resolution.py
test_p3_s33_m05_bundle.py
test_p3_s33_integration.py
test_p3_s33_schemas_and_architecture.py
```

## Invariantes testadas

- manifesto P2 não contém rows;
- painel ausente bloqueia operações granularmente;
- storage paths não são expostos;
- P1 órfã ou hash divergente não é autorizada;
- moving `decision_time` backward does not increase visibility;
- future records and missing times are rejected;
- historical aliases obey validity intervals;
- ambiguity is returned rather than silently resolved;
- aliases and outputs are deterministic;
- bundle contains four read-only offline ports;
- all S33 schemas validate under JSON Schema Draft 2020-12;
- legacy module/schema registries remain isolated.

## Execução segura

Os testes devem ser executados em lotes curtos, com `PYTHONDONTWRITEBYTECODE=1`, cache do pytest desativado e `timeout`. O comando monolítico de release só deve ser usado depois da limpeza de caches.
