# Point in Time

Regras universais:

1. `decision_time` vem do runtime;
2. `available_at <= decision_time`;
3. filtro temporal antes de retrieval, ranking ou cálculo;
4. revisões macro futuras são rejeitadas;
5. ações corporativas só entram após anúncio/disponibilidade;
6. contratos de opções precisam existir historicamente;
7. índices, caches e prompts são snapshot-bound;
8. rede é proibida em backtest;
9. P1 só é acessada por referência autorizada pela P2;
10. todo resultado inclui prova temporal e provenance.
