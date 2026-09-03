# Testes e segurança

O runner seguro executa etapas sequenciais com timeout:

1. validação estrutural do bundle;
2. cópia temporária da P3 base;
3. merge aditivo;
4. compilação;
5. testes de integração unificados.

A validação de release também executa separadamente as suítes funcionais originais de S35, S36 e S37 contra a árvore mesclada. Nenhum processo paralelo, `fork` ou `pytest-xdist` é necessário.
