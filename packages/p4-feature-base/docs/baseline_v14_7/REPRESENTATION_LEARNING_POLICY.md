# Política final de representation learning

## Ordem obrigatória

1. matriz interpretável;
2. seleção estrutural;
3. PCA/Sparse PCA por família;
4. encoder opcional.

Sparse PCA é o champion inicial. O encoder é um único challenger, não uma coleção de arquiteturas.

## Encoder autorizado

- uma camada oculta;
- Huber loss observada e balanceada por grupo;
- 10% de masking;
- 10% de modality dropout;
- AdamW, GELU e parâmetros fixos;
- apenas bottleneck 25% versus 12,5%;
- três seeds por configuração;
- cross-fitting cronológico;
- sem retorno futuro ou objetivo preditivo.

## Gate de necessidade

O encoder não é executado se Sparse PCA preservar a estrutura adequadamente ou se a amostra for insuficiente. A saída `underlying_feature_embeddings` pode ser um artefato explicitamente `NOT_PRODUCED_NOT_AUTHORIZED`, sem quebrar o handoff.
