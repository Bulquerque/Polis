# Visão geral — Fase 0 Guardiã Zero Trust

A Fase 0 é o control plane técnico da arquitetura V14.1 RC4.1. Todas as fases econômicas reportam saúde técnica para ela. Ela emite status PASS/WARN/FAIL, mas não altera outputs econômicos.

## Responsabilidades

1. Registrar fases, subfases, módulos e artefatos.
2. Validar contratos e schemas.
3. Validar hashes, lineage e imutabilidade.
4. Orquestrar evidências de testes.
5. Detectar bloat, duplicata, imports proibidos e estado global escondido.
6. Construir dashboards técnicos.
7. Validar skills, prompts e pacotes de agentes.
8. Decidir release gate técnico.
9. Despachar feedback Zero Trust para as fases.


## RC4.1 — Fonte única

A Fase 0 contém `source_of_truth/`, que governa padrões transversais de código, teste, artefatos, documentação e execução dos agentes.
