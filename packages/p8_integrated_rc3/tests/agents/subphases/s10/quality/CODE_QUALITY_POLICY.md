# Code quality policy

- máximo de 350 linhas por arquivo Python;
- máximo de 60 linhas por função;
- `strict=True`, `frozen=True`, `extra="forbid"` nas fronteiras;
- sem `Any` no domínio econômico;
- sem broad catch que converta erro de integridade em ausência;
- sem timestamps, IDs ou resultados `PASS` gerados por default;
- sem import de internals S8 ou `_module_executor` P9 RC4.1;
- cobertura combinada mínima: 94%;
- schemas Draft 2020-12 válidos;
- release com promotion lock permanente.
