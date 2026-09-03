# Arquitetura

```text
P1 snapshots/raw custody
        ↓
P2 clean macro panels + available_at
        ↓
P3.S33 PIT boundary contract
        ↓
P3.S37 catalog + handlers + qualification
        ↓
P3.S40 composite gateway/evidence
        ↓
P3.S21 cognition
```

## Camadas internas

- contratos: requests, results, catálogo e qualificação;
- normalização: aliases de campos upstream sem fabricar semântica;
- boundary: consulta offline e filtro temporal;
- catálogo: identidade, unidade, frequência, release e readiness;
- handlers: operações públicas;
- qualification: matriz operação × modo;
- wrappers: integração fina com o pipeline canônico.

A lógica de domínio não importa S21, adapters HTTP ou módulos anteriores.
