# Freeze de contratos e controle de mudança

## Contract Freeze Gate
Congela: inputs/outputs, schemas, module IDs, producers, forbidden fields, error-code namespaces, execution stages e path ownership.

## Depois do freeze
Agentes de implementação tratam `contracts/`, `schemas/` e `registries/` como read-only. Qualquer insuficiência gera `change_requests/CR-*.yaml` usando o schema oficial.

## Aprovação
Uma mudança só é aprovada pelo Contract Lead depois de:
1. impacto cross-phase;
2. compatibilidade P2/P3/P5/P0;
3. atualização de contrato, schema, testes e changelog;
4. revalidação documental;
5. comunicação a todos os work packages afetados.

## Proibição
Não é permitido “ajustar o contrato para fazer o teste passar” dentro do branch de implementação.
