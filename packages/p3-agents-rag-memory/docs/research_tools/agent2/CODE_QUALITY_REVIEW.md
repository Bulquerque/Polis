# Revisão de qualidade de código

A unificação preservou o código qualificado de S35, S36 e S37 sem introduzir um executor genérico ou duplicar contratos.

## Resultado

- 81 arquivos Python na extensão;
- 8.874 LOC lógicas;
- 15 wrappers canônicos;
- nenhuma colisão com os 81 wrappers antigos;
- nenhuma importação de rede proibida;
- nenhuma dependência direta com P5;
- nenhuma dependência cruzada entre corpus/macro e outras famílias.

## Gatilhos revisados

Foram encontrados cinco arquivos acima de 300 LOC, oito funções acima de 50 linhas e quatro funções acima do gatilho de complexidade 12. Esses limites são gatilhos de revisão, não falhas automáticas. A decisão foi preservar o comportamento já testado durante a unificação e registrar os pontos para uma versão minor posterior à composição S40.

A comunicação interna entre `market` e `options` é permitida dentro da mesma suite S36. As duas são famílias públicas separadas, mas compartilham contratos de observação; nenhuma dependência alcança corpus ou macro.
