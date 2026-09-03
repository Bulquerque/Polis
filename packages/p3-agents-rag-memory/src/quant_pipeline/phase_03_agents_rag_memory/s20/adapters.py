from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..adapters.nim_endpoint import normalize_nvidia_nim_endpoint
from ..governance.live_safety import EgressPolicy, validate_endpoint
from .models import GraphArtifact, GraphConfig, QueryPanel, RetrievalBundle
from .ports import GraphQueryPort, RerankerPort, TokenizerPort


class RegexTokenizer(TokenizerPort):
    """Small deterministic fallback tokenizer for offline tests and replay."""

    @property
    def ref(self) -> str:
        return "deterministic_regex_v1"

    def count(self, text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


@dataclass(frozen=True)
class StaticReranker(RerankerPort):
    """Deterministic reranker fixture that returns predeclared scores."""

    scores: tuple[float, ...]

    @property
    def ref(self) -> str:
        return "static_reranker_v1"

    def rank(
        self,
        query: str,
        passages: tuple[str, ...],
    ) -> tuple[float, ...]:
        del query
        if len(self.scores) != len(passages):
            raise ValueError("score/passages length mismatch")
        return self.scores


class NvidiaNimClient:
    """Optional HTTPX-compatible NVIDIA NIM adapter.

    The core never imports HTTPX or NVIDIA types. Any client exposing ``post``
    with the HTTPX response surface can be injected, including MockTransport
    based clients in tests.
    """

    def __init__(
        self,
        client: Any,
        base_url: str,
        model: str,
        api_key: str | None = None,
        allow_local: bool = False,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        from urllib.parse import urlsplit
        parsed = urlsplit(self.base_url)
        host = parsed.hostname or ""
        local = host.lower().strip(".") in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}
        decision = validate_endpoint(
            self.base_url,
            EgressPolicy(
                allowed_hosts=(host,),
                allowed_schemes=(parsed.scheme,),
                allowed_ports=(parsed.port or (443 if parsed.scheme == "https" else 80),),
                allow_local_endpoints=allow_local and local,
                forbid_private_networks=not (allow_local and local),
            ),
        )
        if not decision.allowed:
            raise ValueError(f"NVIDIA endpoint rejected by egress policy: {decision.reason_codes}")

    def _headers(self) -> dict[str, str]:
        if self.api_key is None:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def ref(self) -> str:
        return f"nvidia_nim:{self.model}"

    def embeddings(
        self,
        texts: tuple[str, ...],
        input_type: str = "query",
    ) -> tuple[tuple[float, ...], ...]:
        response = self.client.post(
            normalize_nvidia_nim_endpoint(self.base_url, "embeddings"),
            json={
                "model": self.model,
                "input": list(texts),
                "input_type": input_type,
                "truncate": "NONE",
            },
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        rows = sorted(data["data"], key=lambda row: row["index"])
        return tuple(tuple(row["embedding"]) for row in rows)

    def rank(
        self,
        query: str,
        passages: tuple[str, ...],
    ) -> tuple[float, ...]:
        payload = {
            "model": self.model,
            "query": {"text": query},
            "passages": [{"text": passage} for passage in passages],
            "truncate": "NONE",
        }
        response = self.client.post(
            normalize_nvidia_nim_endpoint(self.base_url, "ranking"),
            json=payload,
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        scores = [0.0] * len(passages)
        for row in data["rankings"]:
            scores[row["index"]] = float(
                row.get("logit", row.get("score", 0.0))
            )
        return tuple(scores)

    def tokenize(self, text: str) -> int:
        response = self.client.post(
            normalize_nvidia_nim_endpoint(self.base_url, "tokenize"),
            json={"model": self.model, "prompt": text},
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        return len(data.get("tokens", data.get("token_ids", [])))


class PortableGraphQueryPort(GraphQueryPort):
    """Deterministic query adapter over a persisted portable graph artifact."""

    @property
    def ref(self) -> str:
        return "portable_graph_query_v1"

    def query(
        self,
        queries: QueryPanel,
        graph: GraphArtifact,
        config: GraphConfig,
        *,
        top_k: int,
    ) -> RetrievalBundle:
        from .core import retrieve_graph

        return retrieve_graph(queries, graph, config, top_k=top_k)
