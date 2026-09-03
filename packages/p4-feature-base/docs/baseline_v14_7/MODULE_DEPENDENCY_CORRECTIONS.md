# Correções de dependência V14.6-RC1

- S3.M05 passou a consumir specs validadas e emitir o único execution registry autorizado.
- S3.M03/M04 executam somente observers aprovados.
- S4 recebe o registry aprovado para impedir materialização acidental.
- S5 deixou de consumir o bundle atômico completo e usa bundles mínimos por família.
- S6.M03 recebe somente interações aprovadas.
- S7 separa estados de transform e neutralização antes de gerar o manifest consolidado.
- S8 distingue encoder não autorizado, não executado, concluído e falho não bloqueante.
- S9.M05 foi movido para `post_handoff_qualification`.
- S9.M06 recebe um event log explícito produzido pelo runtime, preservando todas as tentativas.
