# Compatibilidade de APIs e portas

## APIs externas

A P3.S35 não exige API externa em runtime. Em backtest, rede é proibida.

## Portas opcionais

### DenseRetrievalPort

```python
search(query, candidate_chunk_ids, top_k) -> Mapping[str, float]
```

Requisitos:

- retornar somente IDs candidatos;
- scores finitos e não negativos;
- snapshot imutável;
- nenhuma consulta live em backtest.

### RerankerPort

```python
rank(query, passages) -> tuple[float, ...]
```

Requisitos:

- exatamente um score por passage;
- ordem preservada;
- modelo/revisão snapshot-pinned.

### RawEvidenceResolverPort

Resolve bytes P1 somente com lineage autorizada. O handler valida o hash devolvido. Em falha, usa conteúdo reconstruído e marca o resultado como degradado.

### ProvenanceQueryPort

Fornece IDs e hashes P1/P2 conhecidos em `decision_time`. Não pode revelar uma versão futura.

## S12

A compatibilidade é feita contra:

- `RetrievalIndexManifest`;
- `ArtifactRef`;
- `Chunk`;
- `ArtifactStorePort`.

## S21

O envelope S35 é JSON-serializável e cabe em `ToolExecutionResponse.canonical_payload`. Não utiliza campos proibidos como sinal, ranking de candidato, decisão de trade ou peso de portfólio.
