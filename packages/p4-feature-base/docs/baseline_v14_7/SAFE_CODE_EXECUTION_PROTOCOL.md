# Protocolo seguro para código Python

## Regra de confiança

Todo Python recebido ou preservado em `legacy_reference/` é conteúdo não confiável até passar pela auditoria estática.

## Sequência obrigatória

1. listar membros do ZIP sem extrair;
2. rejeitar path traversal, symlinks, membros enormes e expansão excessiva;
3. extrair em diretório descartável;
4. procurar binários, bytecode e arquivos executáveis;
5. analisar AST sem importar módulos;
6. identificar top-level calls, `eval`, `exec`, subprocessos, shell, rede e loops de risco;
7. somente depois, se necessário, executar um alvo explicitamente escolhido com timeout, memória e processo isolados;
8. nunca executar recursivamente todos os scripts.

## Este pacote

A validação documental ativa apenas lê YAML/CSV/Markdown. O código legado permanece quarentenado e não é importado pelo validador. O relatório está em `qualification/STATIC_PYTHON_AUDIT_REPORT.md`.
