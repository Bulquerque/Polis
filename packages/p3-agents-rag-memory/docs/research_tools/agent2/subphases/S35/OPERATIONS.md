# Operações públicas

## search

Pesquisa chunks visíveis. Filtros: fonte, documento, tipo, entidade, underlying e intervalo de disponibilidade.

## get_document

Monta um documento a partir dos chunks visíveis. Pode resolver bytes P1 por porta autorizada. Falha de bytes/hashes gera fallback explícito para o índice.

## compare_versions

Compara duas versões por tokens e hashes. `FORENSIC` requer `version_group_id` confirmado.

## find_counterevidence

Executa consultas contrárias fornecidas pelo planner, respeitando orçamento interno e deduplicação.

## build_timeline

Agrupa chunks por documento e cria eventos ordenados. Relações observadas são separadas de hipóteses.

## inspect_provenance

Monta grafo namespaced:

```text
source:<id>
p1:<artifact_id>
p2:<record_id>
chunk:<chunk_id>
```

A ausência de P1 resulta em proveniência parcial e status degradado.
