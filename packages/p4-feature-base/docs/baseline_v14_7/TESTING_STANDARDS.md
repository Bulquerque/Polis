# Testing standards — addendum P4

A Fase 0 possui testes globais. A P4 possui testes locais de contratos, temporalidade, matemática, replay e integração de fronteira.

Obrigatório por módulo:
- happy path mínimo;
- input/schema negativo;
- forbidden fields;
- point-in-time;
- lineage;
- replay determinístico;
- oracle numérico ou teste metamórfico quando houver cálculo.

Obrigatório por subfase:
- mini-run determinístico;
- missingness e upstream degradado;
- nenhuma rede em unit tests;
- timeout explícito em testes de encoder e integração.
