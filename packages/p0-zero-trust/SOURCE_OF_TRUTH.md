# Source of Truth Binding — P0

Este pacote contém um espelho de compatibilidade da fonte normativa master. A autoridade única está em `global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/source_of_truth/`.

Este pacote segue a fonte única de verdade da RC4.1:

```text
global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/source_of_truth/
```

## Documentos canônicos

- `CODE_STANDARDS.md` → `source_of_truth/standards/CODE_STANDARDS.md`
- `TESTING_STANDARDS.md` → `source_of_truth/standards/TESTING_STANDARDS.md`
- `ZERO_TRUST_RULES.md` → `source_of_truth/standards/ZERO_TRUST_RULES.md`
- `ARTIFACT_STYLE_GUIDE.md` → `source_of_truth/standards/ARTIFACT_STYLE_GUIDE.md`
- `MINIMAL_CODE_POLICY.md` → `source_of_truth/standards/MINIMAL_CODE_POLICY.md`
- `SEARCH_FIRST_PATCH_ONLY_POLICY.md` → `source_of_truth/standards/SEARCH_FIRST_PATCH_ONLY_POLICY.md`
- `POINT_IN_TIME_AI_POLICY.md` → `source_of_truth/standards/POINT_IN_TIME_AI_POLICY.md`

## Regra para agentes

1. Procurar antes de criar.
2. Editar apenas o necessário.
3. Reutilizar `quant_pipeline.common` para utilitários transversais.
4. Criar arquivo novo somente com justificativa e atualização do manifesto.
5. Não duplicar testes globais da Fase 0 dentro desta fase.
