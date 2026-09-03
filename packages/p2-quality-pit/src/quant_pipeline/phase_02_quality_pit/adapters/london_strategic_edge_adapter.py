"""Provider-isolated London Strategic Edge HTTP adapter.

It never fabricates coverage: authentication, response windows and raw bytes
are retained by the caller and a missing key is an explicit qualification
state rather than a PASS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Capture:
    request_url: str
    retrieved_at: str
    status_code: int
    raw_sha256: str
    raw_bytes: int
    payload: object
    raw: bytes


class LondonStrategicEdgeAdapter:
    provider_id = "LONDON_STRATEGIC_EDGE"
    base_url = "https://api.londonstrategicedge.com"

    def __init__(self, api_key: str | None, base_url: str | None = None, timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = (base_url or self.base_url).rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, params: dict[str, str]) -> Capture:
        if not self.api_key:
            raise RuntimeError("LSE_API_KEY_REQUIRED_FOR_US_QUALIFICATION")
        query = dict(params)
        url = f"{self.base_url}/{path.lstrip('/')}?{urlencode(query)}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "P2-US-Qualification/1.0", "X-API-Key": self.api_key})
        retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read()
            status = int(response.status)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("LSE_RESPONSE_NOT_JSON") from exc
        return Capture(url, retrieved, status, sha256(raw).hexdigest(), len(raw), payload, raw)

    def candles(self, symbol: str, start: str, end: str, resolution: str = "1d") -> Capture:
        return self._request("vault/candles", {"symbol": symbol, "timeframe": resolution, "start": start, "end": end, "limit": "5000"})

    def options(self, underlying: str, start: str, end: str) -> Capture:
        # The chain endpoint is the authoritative contract identity snapshot.
        # Historical observations are obtained separately through options_flow.
        return self._request("vault/options/chain", {"underlying": underlying, "limit": "5000"})

    def options_flow(self, underlying: str, start: str, end: str) -> Capture:
        """Return timestamped option prints for the requested historical window."""
        return self._request("vault/options/flow", {"underlying": underlying, "start": start, "end": end, "limit": "5000"})

    def option_candles(self, ticker: str, start: str, end: str) -> Capture:
        """Return historical one-minute premium bars for an exact OPRA ticker."""
        if not ticker:
            raise ValueError("LSE option history requires exact ticker")
        return self._request("vault/options/candles", {"ticker": ticker, "start": start, "end": end, "order": "asc", "limit": "5000"})

    @staticmethod
    def canonical_underlying(symbol: str) -> str:
        return f"US:NASDAQ:EQUITY:{symbol.upper()}"

    @staticmethod
    def canonical_option(osi_symbol: str) -> str:
        if not osi_symbol:
            raise ValueError("US option requires provider contract identity")
        return f"US:OPRA:OPTION:{osi_symbol.upper()}"
