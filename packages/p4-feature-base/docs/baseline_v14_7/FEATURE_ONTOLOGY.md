# Ontologia de features — V14.6-RC1

A ontologia usa cinco níveis:

1. `phenomenon_id`: fenômeno econômico;
2. `perspective_id`: mecanismo/view;
3. `observer_id`: fórmula causal concreta;
4. `parameterization_id`: variante pré-registrada;
5. `feature_realization`: valor por entidade e decision_time.

As dez famílias oficiais estão em `registries/VARIABLE_FAMILY_REGISTRY.yaml`.

## Regras

- fonte de dados não é família econômica;
- técnica estatística não é fenômeno;
- pequenas mudanças de janela não criam novas teorias;
- toda feature carrega disponibilidade, missingness, qualidade, horizonte e lineage;
- todo observer declara racional, falhas conhecidas e modalidades;
- seleção supervisionada pertence à P5.
