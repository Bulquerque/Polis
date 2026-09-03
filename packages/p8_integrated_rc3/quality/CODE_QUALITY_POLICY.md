# Política de Qualidade

- contratos externos Pydantic estritos e `extra=forbid`;
- nenhuma captura ampla que transforme erro de integridade em indisponibilidade;
- nenhuma rede ou filesystem oculto no domínio;
- nenhum `Any` cru atravessa fronteira econômica;
- IDs e hashes preservados por receipt;
- testes unitários, negativos, de contrato, integração e metamórficos;
- nenhum cache, `.pyc`, `.egg-info`, `.coverage` ou `.pytest_cache` entra no ZIP final;
- uma única versão em `version.py` e `pyproject.toml`;
- mudanças em contracts exigem versionamento explícito;
- produção permanece bloqueada sem P9/P0.
