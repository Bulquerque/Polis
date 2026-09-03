# Interpretação do diagrama — Fase 2 — Qualidade, Harmonização e Point-in-Time — RC4.1

O diagrama principal deve ser lido junto com `MODULE_IO_MATRIX.yaml`. As setas entre fases continuam congeladas pela matriz global. As setas internas agora indicam produtores e consumidores explícitos por módulo.

## Função visual

lê artefatos brutos e produz painéis limpos/PIT para Fase 3, 4 e 6, sem features, previsão ou candidato.

## Regra de leitura

1. Entradas externas da fase são validadas na primeira subfase.
2. Artefatos opcionais de feedback entram em ramo paralelo e não bloqueiam o primeiro ciclo.
3. Outputs oficiais só aparecem depois de módulo produtor declarado.
4. Nenhum módulo pode consumir output de fase futura ou emitir campo proibido.

## Correções de subfase aplicadas

A RC4.1 corrige os problemas encontrados nas auditorias: produtores ausentes, inputs oficiais não consumidos, feedback opcional no caminho principal, fluxos lineares falsos e snapshots/handoffs incompletos.

## Correção módulo a módulo — RC4.1

Esta fase foi revisada após auditoria módulo a módulo. O fluxo operacional oficial agora é o declarado em `contracts/MODULE_IO_MATRIX.yaml` e em `modules/*.yaml`. Relações genéricas foram substituídas por produtores/consumidores explícitos.

