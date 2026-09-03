
# Testes do P3 Reformed Plan

Há dois níveis distintos:

1. **`plan_validation/`** — testes executáveis do pacote de plano: estrutura, contratos, DAG, schemas, fixtures, documentação e consistência.
2. **`specifications/`** — especificações obrigatórias para o runtime futuro. Elas não provam que LLM, RAG, MCP ou sociedade já funcionam.

Execute a validação estrutural com:

```bash
pytest -q -p no:cacheprovider tests/plan_validation
```
