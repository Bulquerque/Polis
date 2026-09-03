from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ipaddress
import json
import random
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, build_opener

from ..core import sanitize_url


@dataclass(frozen=True)
class TransportResponse:
    content: bytes
    status: int
    headers: dict[str, str]
    url: str
    requested_at: str
    retrieved_at: str
    retry_count: int


class TransportError(RuntimeError):
    def __init__(self, message: str, *, code: str, status: int | None = None, retry_count: int = 0):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retry_count = retry_count


class HttpClient:
    """Small read-oriented HTTP transport with fail-closed scheme/method policy."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        opener=None,
        allow_insecure_http: bool = False,
        max_response_bytes: int = 256 * 1024 * 1024,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.opener = opener or build_opener()
        self.allow_insecure_http = allow_insecure_http
        self.max_response_bytes = int(max_response_bytes)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Any | None = None,
        data: bytes | None = None,
    ) -> TransportResponse:
        method = method.upper()
        if method not in {"GET", "HEAD", "POST"}:
            raise TransportError(f"HTTP method is not allowed for ingestion: {method}", code="METHOD_NOT_ALLOWED")
        final_url = self._with_params(url, params)
        self._validate_url(final_url)
        body = data
        hdrs = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        retry_count = 0
        while True:
            requested_at = _now()
            req = Request(final_url, data=body, headers=hdrs, method=method)
            try:
                with self.opener.open(req, timeout=self.timeout) as response:
                    response_url = response.geturl()
                    self._validate_url(response_url)
                    content = self._read_bounded(response)
                    return TransportResponse(
                        content=content,
                        status=int(getattr(response, "status", 200)),
                        headers={k.lower(): v for k, v in response.headers.items()},
                        url=sanitize_url(response_url) or sanitize_url(final_url) or "",
                        requested_at=requested_at,
                        retrieved_at=_now(),
                        retry_count=retry_count,
                    )
            except HTTPError as exc:
                status = int(exc.code)
                retryable = status in {408, 425, 429} or 500 <= status < 600
                if retryable and retry_count < self.max_retries:
                    self._sleep_retry(exc.headers, retry_count)
                    retry_count += 1
                    continue
                code = _http_error_code(status)
                raise TransportError(
                    f"HTTP request failed ({status}) for {sanitize_url(final_url)}",
                    code=code, status=status, retry_count=retry_count,
                ) from exc
            except URLError as exc:
                if retry_count < self.max_retries:
                    self._sleep_retry({}, retry_count)
                    retry_count += 1
                    continue
                reason = str(getattr(exc, "reason", exc))
                code = "TIMEOUT" if "timed out" in reason.lower() else "CONNECTION_ERROR"
                raise TransportError(
                    f"network request failed for {sanitize_url(final_url)}: {reason}",
                    code=code, retry_count=retry_count,
                ) from exc

    def _read_bounded(self, response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if self.max_response_bytes > 0 and size > self.max_response_bytes:
                raise TransportError(
                    "HTTP response exceeded configured in-memory capture limit; use a bulk/streaming provider path",
                    code="RESPONSE_TOO_LARGE",
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _validate_url(self, url: str) -> None:
        split = urlsplit(url)
        scheme = split.scheme.lower()
        if scheme == "https":
            pass
        elif scheme == "http" and self.allow_insecure_http:
            pass
        else:
            raise TransportError(f"URL scheme is not allowed for ingestion: {scheme or '<missing>'}", code="URL_POLICY_VIOLATION")
        host = (split.hostname or "").strip().lower()
        if not host:
            raise TransportError("URL host is required", code="URL_POLICY_VIOLATION")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            raise TransportError("local network destinations are blocked", code="URL_POLICY_VIOLATION")
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            addr = None
        if addr is not None and (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast):
            raise TransportError("private/local network destinations are blocked", code="URL_POLICY_VIOLATION")

    @staticmethod
    def _with_params(url: str, params: Mapping[str, Any] | None) -> str:
        if not params:
            return url
        split = urlsplit(url)
        items = list(parse_qsl(split.query, keep_blank_values=True))
        for key, value in params.items():
            if isinstance(value, (list, tuple)):
                items.extend((str(key), str(item)) for item in value)
            elif value is not None:
                items.append((str(key), str(value)))
        return urlunsplit((split.scheme, split.netloc, split.path, urlencode(items), split.fragment))

    def _sleep_retry(self, headers: Mapping[str, Any], retry_count: int) -> None:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        delay = None
        if retry_after:
            try:
                delay = min(float(retry_after), 60.0)
            except (TypeError, ValueError):
                try:
                    dt = parsedate_to_datetime(str(retry_after))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    delay = max(0.0, min((dt - datetime.now(timezone.utc)).total_seconds(), 60.0))
                except Exception:
                    delay = None
        if delay is None:
            delay = min(self.backoff_base * (2 ** retry_count) + random.uniform(0, self.backoff_base), 30.0)
        if delay > 0:
            time.sleep(delay)


def _http_error_code(status: int) -> str:
    return {
        400: "INVALID_REQUEST",
        401: "AUTH_FAILURE",
        402: "QUOTA_EXHAUSTED",
        403: "PERMISSION_DENIED",
        404: "RESOURCE_NOT_FOUND",
        408: "TIMEOUT",
        409: "CONFLICT",
        429: "RATE_LIMITED",
    }.get(status, "HTTP_5XX" if status >= 500 else "HTTP_4XX")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
