# Plano de consolidação executado

## Objetivo

Construir uma única P9 sem sobreposição de arquivos, contratos concorrentes ou wrappers artificiais.

## Decisões

1. Cada subfase possui exatamente uma autoridade de runtime.
2. A implementação de S3–S4 foi separada da cópia concorrente de S7–S8.
3. S7–S8 usa exclusivamente a implementação mais completa e já qualificada em conjunto.
4. S5–S6 foi incorporada como bloco funcional completo, sem stubs.
5. S9–S10 foi incorporada a partir do staging cuja composição já havia sido validada.
6. S1–S2 foi movida para a topologia canônica sem alterar seus contratos públicos.
7. Toda tradução entre modelos diferentes ocorre em adapters tipados.

## Etapas realizadas

```text
inventário
→ escolha de autoridade
→ cópia seletiva
→ remoção de sobreposição
→ normalização do namespace
→ neutralização de nomes
→ adapters de fronteira
→ reintegração dos testes
→ suíte global
→ manifest e release limpa
```

## Critério contra arquitetura Frankenstein

A árvore não contém:

- duas implementações para o mesmo módulo;
- instalação dependente da ordem das wheels;
- merge linha a linha entre modelos de domínio diferentes;
- executor universal criado apenas para esconder incompatibilidades;
- stubs que retornam sucesso;
- contratos convertidos por `model_dump` genérico;
- aliases administrativos como autoridade canônica.
