# Fundamentação técnica

A implementação usa as referências como fundamentação arquitetural, não copia código desses projetos.

## Recuperação lexical e híbrida

- Robertson, S.; Zaragoza, H. **The Probabilistic Relevance Framework: BM25 and Beyond**. Foundations and Trends in Information Retrieval, 2009. DOI: 10.1561/1500000019.
- Cormack, G.; Clarke, C.; Büttcher, S. **Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods**. SIGIR, 2009. DOI: 10.1145/1571941.1572114.
- Karpukhin et al. **Dense Passage Retrieval for Open-Domain Question Answering**. EMNLP 2020, arXiv:2004.04906.
- Khattab; Zaharia. **ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT**. SIGIR 2020, arXiv:2004.12832.

Aplicação:

- BM25 é o baseline local e reproduzível;
- RRF funde rankings sem pressupor escalas calibradas;
- dense retrieval e late interaction ficam atrás de portas opcionais e snapshot-pinned.

## Pesquisa iterativa por agentes

- Yao et al. **ReAct: Synergizing Reasoning and Acting in Language Models**, arXiv:2210.03629.
- Trivedi et al. **Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions**, arXiv:2212.10509.

Aplicação:

- o LLM escolhe uma operação estruturada;
- subconsultas são limitadas por modo e auditadas;
- o handler retorna evidência, não uma crença pronta.

## Proveniência

- W3C. **PROV-O: The PROV Ontology**, Recommendation, 2013.

Aplicação:

- nós de fonte, P1, P2 e chunk são separados;
- relações de derivação e atribuição são explícitas;
- IDs recebem namespace para impedir colisão entre camadas.

## Repositórios de referência

- `castorini/pyserini`: recuperação sparse, dense e híbrida reproduzível.
- `stanford-futuredata/ColBERT`: late interaction e indexação pré-computada.

Esses repositórios não são dependências obrigatórias do pacote.
