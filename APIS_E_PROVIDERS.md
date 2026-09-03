# APIs e provedores configurados

Este documento registra a ordem de provedores e as regras de uso. Credenciais ficam somente no `.env`; nunca copie segredos para código, fixtures, logs ou documentação.

## Prioridade

| Domínio | Principal | Fallbacks | Uso |
|---|---|---|---|
| Dados de mercado | London Strategic Edge | FMP, Finnhub, Alpaca, Alpha Vantage, Marketstack, BRAPI | P1 captura raw; P2 validação PIT |
| Opções | London Strategic Edge | B3/COTAHIST por venue; sem Alpha Vantage premium | LSE é principal internacional/US; B3 é principal brasileiro |
| Macroenergia | FRED/EIA | Alpha Vantage | Séries com `available_at` |
| Notícias/pesquisa | MarketAux | GDELT, Alpha Vantage NEWS_SENTIMENT | Contexto documental validado |
| Inferência LLM | NVIDIA NIM | Nenhum fallback externo | Somente pelo roteador de modelo |

Fallback não mistura séries automaticamente. Toda troca deve registrar `provider`, `dataset`, `request_id`, timestamp, status, hash da resposta e motivo.

## Carregamento seguro

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^#][^=]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
```

```python
from os import environ
from dotenv import load_dotenv

load_dotenv()
lse_key = environ["LSE_API_KEY"]
nvidia_key = environ["NVIDIA_API_KEY"]
```

Nunca imprima valores de variáveis; registre apenas `configured=true/false`.

## London Strategic Edge

Variáveis: `LSE_API_KEY`, `LSE_BASE_URL` e, opcionalmente, `LSE_PROBE_URL`. O superteste usa o SDK `lse-data` quando instalado; uma URL pública sem rota de dados nunca é inferida como endpoint.

O cliente deve preservar a resposta original, respeitar quota, paginar e produzir hash/snapshot. O SDK `lse-data` fornece candles de underlying e de opção, mas candles não equivalem a bid/ask; sem essas pontas a lane não é promovida ao backtest. WebSocket permanece separado do primeiro slice histórico.

## Fallbacks de mercado

- FMP: `FMP_API_KEY`
- Finnhub: `FINNHUB_API_KEY`
- Alpaca: `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`
- Alpha Vantage: `ALPHA_VANTAGE_API_KEY`
- Marketstack: `MARKETSTACK_API_KEY`
- BRAPI: sem chave; somente snapshot de underlying brasileiro, nunca opções

MarketAux permanece opcional. GDELT (`https://api.gdeltproject.org/api/v2/doc/doc`) é o fallback sem chave para notícias; suas respostas entram como contexto independente e não são misturadas com séries de mercado. BRAPI (`https://brapi.dev/api/quote/{symbol}`) é apenas um fallback de preço de ações brasileiras. Nenhum dos dois é fonte de opções.

FMP é sondado pela rota `stable/quote`; a rota legada `api/v3/profile` não é usada, pois a própria documentação informa restrições para APIs legadas.

Os testes de opções aceitam somente payloads com contrato identificável. London Strategic Edge é a fonte principal para opções internacionais/US e B3/COTAHIST é a fonte principal para opções brasileiras. Alpha Vantage e Czar28 são capturadores legados opcionais e não participam do gate de prontidão. LSE/B3 podem produzir captura indicativa sem bid/ask; nesse caso a captura é preservada e classificada explicitamente, sem sintetizar quotes e sem prometer elegibilidade para backtest de execução.

Alpaca exige uma distinção adicional: o endpoint de snapshots/latest quotes pode entregar bid/ask, mas isso prova apenas um snapshot. A série histórica depende do endpoint histórico, da janela disponível e do entitlement do feed (`indicative` ou `OPRA`); barras históricas não são convertidas em quotes. O superteste registra `SINGLE_SNAPSHOT_ONLY`, `HISTORICAL_QUOTE_SERIES_CANDIDATE` ou `NO_EXECUTABLE_BID_ASK` explicitamente, mantendo o gate fechado até existir profundidade temporal no mesmo provedor. Referências: [historical option data](https://docs.alpaca.markets/us/docs/historical-option-data), [latest option quotes](https://docs.alpaca.markets/us/reference/optionlatestquotes).

Dados macro/documentais: `FRED_API_KEY`, `EIA_API_KEY`, `BEA_API_KEY`, `SEC_USER_AGENT`; `BLS_API_KEY` é opcional para a rota pública de série simples. Se o provedor ecoar a credencial no próprio payload, o snapshot é sanitizado e fica fora do handoff exato.

Trading deve permanecer desabilitado por padrão. Toda observação precisa preservar data de referência e data de disponibilidade; revisões posteriores não podem entrar em backtests históricos.

## LLM e modelos

NVIDIA NIM é o único provedor de LLM autorizado neste ambiente e usa `NVIDIA_API_KEY` e `NVIDIA_BASE_URL`. O modelo deve ser recebido do roteador point-in-time ou configurado explicitamente em `NVIDIA_MODEL`; nunca deve ser escolhido por um agente durante a execução.

Cada execução deve registrar `provider`, `model`, `model_version`, `prompt_version`, hashes, latência e tokens — nunca a chave.

## Segurança

Se uma credencial tiver sido exposta no histórico da conversa, ela deve ser revogada e substituída antes do uso em produção.
