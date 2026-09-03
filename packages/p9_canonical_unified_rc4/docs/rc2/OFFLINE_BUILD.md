# Build em ambiente controlado

## Toolchain qualificada

```text
Python 3.13
setuptools 82.0.1
pydantic 2.13.4
numpy 2.3.5
scipy 1.17.0
statsmodels 0.14.6
pytest 9.0.2
jsonschema 4.26.0
PyYAML 6.0.3
```

## Construção da wheel

```bash
python -m pip wheel . --no-build-isolation --no-deps -w dist
```

O ambiente air-gapped deve provisionar previamente as dependências runtime. A ausência de um índice externo não deve ser interpretada como falha do código da P9.
