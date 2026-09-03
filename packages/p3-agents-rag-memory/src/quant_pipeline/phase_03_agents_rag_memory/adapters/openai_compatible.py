from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx

from .nim_endpoint import normalize_nvidia_nim_endpoint
from ..governance.live_safety import EgressPolicy, validate_endpoint
from ..runtime_shared.s21_errors import S21DependencyError
from ..runtime_shared.s21_hashing import content_hash
from ..runtime_shared.s21_models import LLMRequest, LLMResponse


def _nvidia_nim_egress_policy(endpoint_url: str, *, allow_local: bool) -> EgressPolicy:
    parsed = urlsplit(endpoint_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    local = host.lower().strip(".") in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}
    return EgressPolicy(
        allowed_schemes=(parsed.scheme,),
        allowed_hosts=(host,),
        allowed_ports=(port,),
        forbid_private_networks=not (allow_local and local),
        allow_local_endpoints=allow_local and local,
    )


@dataclass(frozen=True, slots=True)
class OpenAICompatibleSettings:
    """Settings for OpenAI-compatible chat-completions providers.

    Credentials belong in the injected HTTP client's headers. They are deliberately
    absent from this model so they cannot leak into Phase 3 artifacts or logs.
    """

    endpoint_url: str
    request_json_object: bool = True
    egress_policy: EgressPolicy | None = None
    raw_response_dir: str | None = None

    @classmethod
    def for_nvidia_nim(
        cls,
        base_url: str,
        *,
        allow_local: bool = False,
        request_json_object: bool = True,
    ) -> "OpenAICompatibleSettings":
        endpoint_url = normalize_nvidia_nim_endpoint(base_url)
        return cls(
            endpoint_url=endpoint_url,
            request_json_object=request_json_object,
            egress_policy=_nvidia_nim_egress_policy(endpoint_url, allow_local=allow_local),
        )

    @classmethod
    def from_nvidia_nim_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        allow_local: bool = True,
    ) -> tuple["OpenAICompatibleSettings", str, dict[str, str]]:
        """Load non-secret endpoint/model metadata and return injectable headers.

        The API key is read only to build the transient HTTP header and is never
        stored in the settings object or emitted by the package's artifacts.
        """
        values = environ or os.environ
        base_url = values.get("NVIDIA_BASE_URL", "http://127.0.0.1:8000/v1")
        model_id = values.get("NVIDIA_MODEL", "").strip()
        if not model_id:
            raise ValueError("NVIDIA_MODEL must be configured for the NIM runtime")
        api_key = values.get("NVIDIA_API_KEY", "").strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        return cls.for_nvidia_nim(base_url, allow_local=allow_local), model_id, headers

    def __post_init__(self) -> None:
        from urllib.parse import urlsplit
        host = urlsplit(self.endpoint_url).hostname or ""
        policy = self.egress_policy or EgressPolicy(allowed_hosts=(host,))
        decision = validate_endpoint(self.endpoint_url, policy)
        if not decision.allowed:
            raise ValueError(f"LLM endpoint rejected by egress policy: {decision.reason_codes}")


class OpenAICompatibleHTTPXLLMAdapter:
    """HTTPX adapter for OpenAI-compatible `/chat/completions` APIs.

    The adapter is suitable for NVIDIA NIM and other qualified providers exposing
    the same response envelope. Provider-specific behavior remains configured in
    the composition root and provider registry, not in the cognition domain.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        settings: OpenAICompatibleSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    @classmethod
    def for_nvidia_nim(
        cls,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        allow_local: bool = False,
    ) -> "OpenAICompatibleHTTPXLLMAdapter":
        return cls(
            client=client,
            settings=OpenAICompatibleSettings.for_nvidia_nim(
                base_url,
                allow_local=allow_local,
            ),
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, object] = {
            "model": request.model_id,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if self._settings.request_json_object:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = None
            for attempt in range(3):
                try:
                    response = await self._client.post(
                        self._settings.endpoint_url,
                        json=payload,
                    )
                except (httpx.TimeoutException, httpx.RequestError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                    response.raise_for_status()
                    break
                await asyncio.sleep(0.25 * (attempt + 1))
        except httpx.TimeoutException as exc:
            raise S21DependencyError(
                code="LLM_HTTP_TIMEOUT",
                message="LLM provider request timed out",
                module_id="P3.S21",
                details={"provider_id": request.provider_id},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise S21DependencyError(
                code="LLM_HTTP_STATUS_ERROR",
                message="LLM provider returned a non-success status",
                module_id="P3.S21",
                details={
                    "provider_id": request.provider_id,
                    "status_code": exc.response.status_code,
                    "request_id": exc.response.headers.get("x-request-id"),
                },
            ) from exc
        except httpx.RequestError as exc:
            raise S21DependencyError(
                code="LLM_HTTP_REQUEST_ERROR",
                message="LLM provider request failed before a valid response",
                module_id="P3.S21",
                details={"provider_id": request.provider_id},
            ) from exc

        try:
            envelope = response.json()
            message = envelope["choices"][0]["message"]
            raw_content = message["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise S21DependencyError(
                code="LLM_RESPONSE_ENVELOPE_INVALID",
                message="provider response does not match the qualified chat-completions envelope",
                module_id="P3.S21",
                details={
                    "provider_id": request.provider_id,
                    "request_id": response.headers.get("x-request-id"),
                },
            ) from exc

        raw_response_ref = self._persist_raw_response(envelope, request)

        if isinstance(raw_content, dict):
            content = raw_content
        elif isinstance(raw_content, str):
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                raise S21DependencyError(
                    code="LLM_RESPONSE_NOT_JSON",
                    message="provider returned non-JSON message content",
                    module_id="P3.S21",
                    details={"provider_id": request.provider_id},
                ) from exc
            if not isinstance(parsed, dict):
                raise S21DependencyError(
                    code="LLM_RESPONSE_JSON_NOT_OBJECT",
                    message="provider JSON content must be an object",
                    module_id="P3.S21",
                    details={"provider_id": request.provider_id},
                )
            content = parsed
        else:
            raise S21DependencyError(
                code="LLM_RESPONSE_CONTENT_INVALID",
                message="provider message content has an unsupported type",
                module_id="P3.S21",
                details={"provider_id": request.provider_id},
            )

        return LLMResponse(
            provider_id=request.provider_id,
            model_id=request.model_id,
            content=content,
            response_hash=content_hash(content),
            raw_response_ref=raw_response_ref or (
                f"http-response://{response.headers.get('x-request-id')}"
                if response.headers.get("x-request-id")
                else None
            ),
        )

    def _persist_raw_response(self, envelope: object, request: LLMRequest) -> str | None:
        """Persist a provider envelope only when the composition root opts in.

        The runtime keeps the provider response outside the typed P3 panels, but
        retains an immutable local copy for replay and audit. The store is
        content-addressed and written atomically so a partial response cannot be
        presented as evidence.
        """
        if not self._settings.raw_response_dir:
            return None
        persisted = {
            "request_identity": {
                "run_id": request.run_id,
                "cycle_id": request.cycle_id,
                "person_id": request.person_id,
                "cognition_transaction_id": request.cognition_transaction_id,
                "stage": request.stage.value,
                "prompt_hash": request.prompt_hash,
            },
            "provider_response": envelope,
        }
        raw = json.dumps(
            persisted, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        root = Path(self._settings.raw_response_dir)
        target = root / digest[:2] / f"{digest}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f".{digest}.", suffix=".tmp", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(raw)
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return f"local-object://llm/{digest}.json"
