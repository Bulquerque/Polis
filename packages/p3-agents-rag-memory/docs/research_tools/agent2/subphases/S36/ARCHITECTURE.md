# Architecture

## Camadas

```text
P2 materialized artifacts
        ↓
P3.S33 boundary contract
        ↓
P3.S36 view binding
        ↓
market/options handlers
        ↓
result envelope + PIT proof + evidence refs
        ↓
P3.S40 handler registry and S21 bridge
```

## Estrutura interna

```text
families/market/
  request_contracts.py
  result_contracts.py
  view_contracts.py
  qualification_contracts.py
  boundary.py
  view_binding.py
  market_handlers.py
  option_handlers.py
  evidence.py
  qualification.py
  handlers.py
  factory.py

families/options/
  surface.py
```

`boundary.py` é um adapter local de qualificação. Produção poderá substituí-lo pelo port da S33 mantendo o comportamento temporal.

## Separação de responsabilidades

- view binding verifica existência e campos por operação;
- handlers consultam apenas ports;
- evidence constrói cobertura, PIT proof e hashes;
- surface calcula diagnósticos puros sobre quotes visíveis;
- qualification declara disponibilidade por `tool × operation × mode`;
- wrappers canônicos apenas validam inputs e delegam.

## Dependências

Obrigatória: Pydantic. PyYAML e pytest são dependências de desenvolvimento. QuantLib e py_vollib não são dependências da V1.
