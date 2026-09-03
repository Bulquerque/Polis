# P3.S33 Applied Reference Research

## FRED/ALFRED

A API oficial permite fornecer `vintage_dates` e períodos de tempo real para recuperar séries como existiam em datas históricas. Isso fundamenta a separação entre período econômico, release, revisão e disponibilidade.

## W3C PROV-O

PROV-O fornece classes e relações para representar a proveniência produzida em sistemas distintos. A extensão aplica um perfil pequeno: entidades de dados, atividades de ingestão/normalização/consulta e agentes ou fontes responsáveis.

## OpenLineage

OpenLineage modela datasets, jobs e runs, com facets extensíveis e schemas formais. A S33 adota a separação conceitual e IDs consistentes, mas mantém a emissão de eventos OpenLineage como adapter opcional futuro.

## GitHub de referência

O repositório oficial OpenLineage contém a especificação formal, JSON Schema e OpenAPI. A implementação local não copia código nem adiciona runtime externo; usa o projeto como referência para nomes, extensibilidade e validação de lineage.
