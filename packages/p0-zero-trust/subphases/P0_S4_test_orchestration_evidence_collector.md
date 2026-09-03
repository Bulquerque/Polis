# P0.S4 — Test Orchestration & Evidence Collector

## Função

A P0.S4 é a autoridade técnica sobre **saúde de testes e evidências pré-qualificação** da Fase 0. Ela não substitui os supertestes/qualification e não interrompe automaticamente outras fases. Ela coleta, normaliza, verifica e classifica evidências para que a Control Tower e o Release Gate saibam o que foi realmente testado e o que ainda não está pronto.

## Módulos

### P0.S4.M01 — Test Report Collector
Coleta quatro famílias de relatórios. É lifecycle-aware: fases não iniciadas podem não emitir runtime test reports sem gerar falso FAIL. Fases que já deveriam testar e não entregam evidência recebem uma lacuna explícita.

### P0.S4.M02 — Contract Test Orchestrator
Executa um oracle independente de contratos. Verifica identidade entre module/contract registries, simetria entre I/O e conexões, schemas de saída e módulos referenciados. A política de conexões proibidas continua sob P0.S1.M05.

### P0.S4.M03 — Schema Test Orchestrator
Executa fixtures válidas e inválidas contra schemas registrados, mede cobertura de classes de mutação e valida paths/hashes quando disponíveis.

### P0.S4.M04 — Test Status Aggregator
Separa evidência reportada pelas fases dos controles independentes da P0. Estados por fase: `NOT_RUN`, `PARTIAL`, `PASS`, `FAIL`. O controle externo permanece `PASS/FAIL`; readiness é outra dimensão.

### P0.S4.M05 — Evidence Package Builder
Cria um pacote content-addressed de evidências obrigatórias e opcionais, categorizado e rastreável. O conjunto obrigatório é governado por policy versionada e pode crescer sem reescrever o módulo.

## Relação com qualification

```text
Module/Phase tests -> P0.S4 -> pre-qualification evidence
                                   |
                                   v
                           Supertest / Qualification
                                   |
                                   v
                         Control Tower / Release
```

A qualification não é input obrigatório de M05 porque isso criaria um ciclo: a qualification da P0 precisa executar a própria S4.
