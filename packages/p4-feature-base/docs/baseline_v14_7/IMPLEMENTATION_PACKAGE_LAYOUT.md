# Layout de implementação recomendado

Os 49 wrappers preservam IDs e nomes contratuais. A lógica vive em nove domínios. O pacote não deve ter um arquivo por fórmula; observers são declarados no registry e executados por kernels reutilizáveis. Crie arquivo novo apenas quando houver responsabilidade distinta e estável.

Tests:
```text
tests/
  unit/<domain>/
  contract/
  property/
  integration/subphase/
  integration/cross_phase/
  fixtures/minimal/
  fixtures/oracles/
```

A Fase 0 continua dona de estrutura global, manifestos globais, conexões e testes transversais.
