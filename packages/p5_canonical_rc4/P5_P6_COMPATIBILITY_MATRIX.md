# P5→P6 compatibility

| Artifact/capability | Current P6 RC6.0-C | P5 policy |
|---|---|---|
| `market_belief_state` | natively consumed and externally validated | strict P6 record shape and content hash |
| terminal-price scenarios | consumed only with a real price anchor | `LIMITED` without anchor; never fabricate spot |
| native ambiguity probabilities | unavailable without compatible price scenarios | `UNAVAILABLE`, not neutral defaults |
| extended return/vol/path artifacts | published by P5 | full consumption pending P6 support |
| extended ambiguity/dependence/regime/confidence | published by P5 | full consumption pending P6 support |
| `underlying_forecast_panel` V1 | temporary adapter projection | preserved; does not replace V2 artifacts |

The manifest separates native P6 capability from extended P5 scientific capability. P7 compatibility is indirect: P7 consumes evaluated P6 candidates, not raw P5 forecasts.
