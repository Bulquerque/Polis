# Contributing

## Before changing code

1. Identify the owner in `docs/MODULE_MAP.md`.
2. Read `docs/BOUNDARY_A_TO_B.md` for cross-domain changes.
3. Do not edit shared contracts without a contract-change request.
4. Add tests using a real producer model.

## Required checks

```bash
p3 validate
pytest -q
python -m compileall -q src tests tools
python tools/release.py validate
```

Connected CI must additionally run Ruff, mypy and `uv sync --locked`.

## Prohibited

- Provider SDK imports outside adapters.
- Hidden clocks, random values or environment reads in domain services.
- Silent defaults at contract boundaries.
- Duplicate schemas for one artifact name.
- Runtime references to historical agent IDs.
- Broad exception handling that returns empty success.
- Adapters that perform I/O or invent semantics.
