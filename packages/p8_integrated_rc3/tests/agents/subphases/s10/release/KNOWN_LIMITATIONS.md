# Known limitations

1. O PBO é uma implementação diagnóstica CSCV limitada a até 6 blocos e 64 combinações; não substitui a análise completa da P9.
2. DSR assume consistência de annualization entre returns e trial Sharpes.
3. O replay model cobre os eventos canônicos necessários para a prova de S10; adapters de eventos S8 devem preservar a semântica.
4. A P9 vNext ainda não está materializada neste pacote. O consumer contract é validado pelo schema/modelo P8→P9.
5. A P9 RC4.1 antiga é semanticamente incompatível e não possui adapter automático.
6. O SBOM é de componentes declarados e ambiente de build; não inclui análise de vulnerabilidades.
7. Promoção produtiva permanece desabilitada.
