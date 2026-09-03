# Pyproject e ferramentas

Alvo de qualificação: Python 3.13, compatível com a P3 atual. Antes de integrar na root, P0 deve confirmar a versão global.

Extras propostos:
- core: pydantic, PyYAML, jsonschema;
- quant: numpy, pandas, scipy, scikit-learn;
- encoder: torch opcional;
- parquet: pyarrow opcional;
- dev: pytest, hypothesis, ruff, mypy, coverage.

Ruff: E/F/I/UP/B/SIM/RUF. Mypy strict no pacote P4. Pytest markers: unit, contract, property, pit, replay, integration, slow, encoder.
