from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx

from ..errors import ProviderAdapterError
from ..models import (
    OpenFigiAdapterConfig,
    OpenFigiCandidate,
    OpenFigiJobResult,
    OpenFigiMappingJob,
)

MODULE_ID = "P3.S17.M02"


class OpenFigiV3Client:
    """Optional OpenFIGI v3 identifier mapper.

    This adapter never chooses among multiple candidates. The domain resolver decides whether
    a result is unique, weighted, ambiguous, or unresolved.
    """

    def __init__(
        self,
        *,
        config: OpenFigiAdapterConfig,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=config.follow_redirects,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            trust_env=False,
        )

    async def __aenter__(self) -> OpenFigiV3Client:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def map_jobs(
        self,
        jobs: Sequence[OpenFigiMappingJob],
    ) -> tuple[OpenFigiJobResult, ...]:
        if not jobs:
            return ()
        batch_size = (
            self._config.authenticated_batch_size
            if self._api_key
            else self._config.anonymous_batch_size
        )
        results: list[OpenFigiJobResult] = []
        for start in range(0, len(jobs), batch_size):
            batch = tuple(jobs[start : start + batch_size])
            results.extend(await self._request_batch(batch))
        return tuple(results)

    async def _request_batch(
        self,
        jobs: tuple[OpenFigiMappingJob, ...],
    ) -> tuple[OpenFigiJobResult, ...]:
        payload = [_job_payload(job) for job in jobs]
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["X-OPENFIGI-APIKEY"] = self._api_key

        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.post("/v3/mapping", json=payload, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_error = exc
                if attempt >= self._config.max_retries:
                    break
                await asyncio.sleep(_backoff_seconds(attempt, None))
                continue

            if response.status_code == 200:
                return _parse_response(jobs, response)
            if response.status_code in {429, 500, 503} and attempt < self._config.max_retries:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                await asyncio.sleep(_backoff_seconds(attempt, retry_after))
                continue
            raise ProviderAdapterError(
                module_id=MODULE_ID,
                code="P3_S17_M02_PROVIDER_ERROR",
                message="OpenFIGI request failed",
                details={
                    "provider_id": self._config.provider_id,
                    "status_code": response.status_code,
                    "request_count": len(jobs),
                },
            )

        raise ProviderAdapterError(
            module_id=MODULE_ID,
            code="P3_S17_M02_PROVIDER_ERROR",
            message="OpenFIGI request exhausted retry budget",
            details={
                "provider_id": self._config.provider_id,
                "request_count": len(jobs),
                "last_error_type": type(last_error).__name__ if last_error else None,
            },
        )

def _job_payload(job: OpenFigiMappingJob) -> dict[str, str]:
    payload = {"idType": job.id_type, "idValue": job.id_value}
    if job.mic_code:
        payload["micCode"] = job.mic_code
    if job.exchange_code:
        payload["exchCode"] = job.exchange_code
    if job.currency:
        payload["currency"] = job.currency
    return payload


def _parse_response(
    jobs: tuple[OpenFigiMappingJob, ...],
    response: httpx.Response,
) -> tuple[OpenFigiJobResult, ...]:
    raw = response.json()
    if not isinstance(raw, list) or len(raw) != len(jobs):
        raise ProviderAdapterError(
            module_id=MODULE_ID,
            code="P3_S17_M02_PROVIDER_RESPONSE_INVALID",
            message="OpenFIGI response cardinality does not match request",
            details={"expected": len(jobs), "actual": len(raw) if isinstance(raw, list) else None},
        )

    results: list[OpenFigiJobResult] = []
    for job, item in zip(jobs, raw, strict=True):
        if not isinstance(item, dict):
            raise ProviderAdapterError(
                module_id=MODULE_ID,
                code="P3_S17_M02_PROVIDER_RESPONSE_INVALID",
                message="OpenFIGI job result is not an object",
                details={"id_type": job.id_type},
            )
        if "warning" in item:
            results.append(OpenFigiJobResult(job=job, warning=str(item["warning"])))
            continue
        if "error" in item:
            results.append(OpenFigiJobResult(job=job, error=str(item["error"])))
            continue
        data = item.get("data")
        if not isinstance(data, list) or not data:
            raise ProviderAdapterError(
                module_id=MODULE_ID,
                code="P3_S17_M02_PROVIDER_RESPONSE_INVALID",
                message="OpenFIGI result has no data, warning, or error",
                details={"id_type": job.id_type},
            )
        candidates = tuple(_parse_candidate(candidate) for candidate in data)
        results.append(OpenFigiJobResult(job=job, candidates=candidates))
    return tuple(results)


def _parse_candidate(raw: object) -> OpenFigiCandidate:
    if not isinstance(raw, dict) or not isinstance(raw.get("figi"), str):
        raise ProviderAdapterError(
            module_id=MODULE_ID,
            code="P3_S17_M02_PROVIDER_RESPONSE_INVALID",
            message="OpenFIGI candidate is missing figi",
            details={},
        )
    return OpenFigiCandidate(
        figi=raw["figi"],
        ticker=_optional_str(raw.get("ticker")),
        name=_optional_str(raw.get("name")),
        exchange_code=_optional_str(raw.get("exchCode")),
        composite_figi=_optional_str(raw.get("compositeFIGI")),
        share_class_figi=_optional_str(raw.get("shareClassFIGI")),
        security_type=_optional_str(raw.get("securityType")),
        security_type2=_optional_str(raw.get("securityType2")),
        market_sector=_optional_str(raw.get("marketSector")),
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, 60.0)
    return min(0.25 * (2**attempt), 8.0)
