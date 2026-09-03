# P3.S34 Implementation Guide

## Estrutura

```text
contracts/capability_artifacts.py
contracts/capability_configs.py
services/capability_taxonomy.py
services/person_capabilities.py
services/research_plans.py
compatibility/s21_entitlements.py
compatibility/s20_context.py
s34.py
modules/P3_S34_M01...M05
```

## M01 — Taxonomia

Produz `research_capability_taxonomy` e `capability_operation_requirement_matrix`. Os requisitos são derivados do `research_mode_registry`; não existe segunda lista manual por operação. Campos proibidos do schema da pessoa não podem ser reaproveitados como capacidades.

## M02 — Perfil ex ante

Produz um registro por `person_id × capability_id`, com score, nível e componentes explicáveis. O profiler aceita somente características disponíveis antes da decisão: competências, função econômica, instituição, acesso e recursos. Uma chave proibida em qualquer profundidade do input causa falha fechada.

## M03 — Planos

Valida oito planos como DAGs determinísticos. Cada plano possui no máximo cinco unidades de chamada visível por ciclo. Readiness é calculada por operação com base no relatório da S33; nós obrigatórios bloqueados tornam o plano bloqueado.

## M04 — Entitlement S21

Combina capacidade, recursos, views, provider, gateway e restrições legadas. O resultado usa diretamente `runtime_shared.s21_models.PersonToolEntitlementPanel`. `allowed_operations` contém operações funcionais, nunca `DISCOVER/REQUEST/EXECUTE`. O JSON Schema de request é estreitado para os modos permitidos da pessoa.

## M05 — Contexto S20→S21

Projeta o bundle S20 para `ValidatedPersonContextBundle` do S21. Preserva identidade, crenças e evidências; acrescenta somente descriptors de operações autorizadas. A seleção é determinística e limitada pelo token budget. `as_of` precisa ser igual ao `decision_time` do snapshot.

## Código

- modelos Pydantic estritos e imutáveis;
- funções puras;
- ports e projeções explícitas;
- hashes SHA-256 e ordenação estável;
- nenhum wall clock, rede ou estado global;
- wrappers finos, um caso de uso por módulo.
