# Compatibilidade e migração

## De V14.2-RC1 para V14.6-RC1

A topologia de 9 subfases é mantida. Mudanças:

- S4: +M08 fundamentos/contabilidade;
- S5: +M09 value/quality/profitability/investment; +M10 carry/curve/basis;
- S8: novo M01 fold/HPO controller; módulos anteriores renumerados M02–M04;
- S9: novo M03 consumer view packager; handoff/receipt renumerados M04–M05.

## Compatibilidade externa

Os 8 outputs legados continuam. `underlying_feature_embeddings` passa a aceitar estado desativado/ausente documentado, e P5 deve suportar Tier 0/1 sem encoder.

## Migração global

Atualizar tabelas globais, P0 registry, P2 extensions, P5 intake e manifestos antes de marcar a geração como baseline aceita.
