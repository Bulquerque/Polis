from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .base import AdapterConfigurationError, AdapterContext, SourceAdapter


def _json_path(payload: Any, path: str | None):
    if not path:
        return None
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


class ConfiguredHttpAdapter(SourceAdapter):
    adapter_id = "generic_http"
    default_method = "GET"
    credential_mode: str | None = None
    credential_parameter: str | None = None
    allow_post = False

    def fetch_raw(self, task: dict, context: AdapterContext):
        spec = deepcopy(task.get("request_spec") or {})
        url = spec.get("url") or task.get("source_url")
        if not url:
            raise AdapterConfigurationError(f"{self.adapter_id} requires request_spec.url")
        method = str(spec.get("method") or self.default_method).upper()
        if method in {"PUT", "PATCH", "DELETE"}:
            raise AdapterConfigurationError(f"{method} is forbidden in read-only ingestion")
        if method == "POST" and not (self.allow_post or bool(spec.get("read_only_post"))):
            raise AdapterConfigurationError("POST requires an adapter-declared read-only POST capability")
        if method not in {"GET", "HEAD", "POST"}:
            raise AdapterConfigurationError(f"unsupported read-only ingestion method: {method}")
        params = dict(spec.get("params") or {})
        headers = dict(spec.get("headers") or {})
        json_body = spec.get("json")
        raw_data = spec.get("data")
        if isinstance(raw_data, str):
            raw_data = raw_data.encode("utf-8")

        handle = task.get("credential_handle")
        credential = context.credential_resolver.resolve(handle, required=False)
        mode = spec.get("credential_mode") or self.credential_mode
        parameter = spec.get("credential_parameter") or self.credential_parameter
        if credential and mode:
            if mode == "query":
                if not parameter:
                    raise AdapterConfigurationError("credential_parameter is required for query auth")
                params[parameter] = credential
            elif mode == "header":
                if not parameter:
                    raise AdapterConfigurationError("credential_parameter is required for header auth")
                headers[parameter] = credential
            elif mode == "bearer":
                headers[parameter or "Authorization"] = f"Bearer {credential}"
            else:
                raise AdapterConfigurationError(f"unsupported credential mode: {mode}")
        elif task.get("credential_required") and not credential:
            context.credential_resolver.resolve(handle, required=True)

        pagination = spec.get("pagination") or {}
        if not pagination:
            return [context.http_client.request(
                method, url, params=params, headers=headers, json_body=json_body, data=raw_data,
            )]
        return self._fetch_paginated(
            context, method=method, url=url, params=params, headers=headers,
            json_body=json_body, data=raw_data, pagination=pagination,
        )

    def _fetch_paginated(self, context: AdapterContext, *, method, url, params, headers, json_body, data, pagination):
        mode = pagination.get("type") or pagination.get("mode")
        max_pages = int(pagination.get("max_pages", 10000))
        responses = []
        page_params = dict(params)
        page_body = deepcopy(json_body)
        if mode == "offset_total":
            offset_param = pagination.get("offset_param", "offset")
            limit_param = pagination.get("limit_param", "limit")
            page_size = int(pagination.get("page_size", page_params.get(limit_param, 5000)))
            offset = int(pagination.get("start_offset", 0))
            page_params[limit_param] = page_size
            for _ in range(max_pages):
                page_params[offset_param] = offset
                response = context.http_client.request(method, url, params=page_params, headers=headers, json_body=page_body, data=data)
                responses.append(response)
                payload = _decode_json(response.content)
                total = _json_path(payload, pagination.get("total_path"))
                if total is None:
                    raise AdapterConfigurationError("offset_total pagination requires a valid total_path")
                offset += page_size
                if offset >= int(total):
                    return responses
            raise AdapterConfigurationError("pagination exceeded max_pages")
        if mode == "page_total_pages":
            page_param = pagination.get("page_param", "page")
            page = int(pagination.get("start_page", 1))
            for _ in range(max_pages):
                page_params[page_param] = page
                response = context.http_client.request(method, url, params=page_params, headers=headers, json_body=page_body, data=data)
                responses.append(response)
                payload = _decode_json(response.content)
                total_pages = _json_path(payload, pagination.get("total_pages_path"))
                if total_pages is None:
                    raise AdapterConfigurationError("page_total_pages pagination requires total_pages_path")
                if page >= int(total_pages):
                    return responses
                page += 1
            raise AdapterConfigurationError("pagination exceeded max_pages")
        if mode == "next_token":
            token_param = pagination.get("token_param", "page_token")
            token = pagination.get("initial_token")
            seen_tokens = set()
            for _ in range(max_pages):
                if token:
                    token = str(token)
                    if token in seen_tokens:
                        raise AdapterConfigurationError("PAGINATION_BLOCKED: repeated next_page_token")
                    seen_tokens.add(token)
                    page_params[token_param] = token
                response = context.http_client.request(method, url, params=page_params, headers=headers, json_body=page_body, data=data)
                responses.append(response)
                payload = _decode_json(response.content)
                if token and isinstance(payload, dict) and (payload.get("error") or payload.get("error_code")):
                    raise AdapterConfigurationError("PAGINATION_BLOCKED: invalid next_page_token")
                token = _json_path(payload, pagination.get("next_token_path"))
                if not token:
                    return responses
            raise AdapterConfigurationError("PAGINATION_BLOCKED: max_pages_exceeded")
        raise AdapterConfigurationError(f"unsupported pagination type: {mode}")


class FredAdapter(ConfiguredHttpAdapter):
    adapter_id = "fred"
    credential_mode = "query"
    credential_parameter = "api_key"


class EiaAdapter(ConfiguredHttpAdapter):
    adapter_id = "eia"
    credential_mode = "query"
    credential_parameter = "api_key"


class FinnhubAdapter(ConfiguredHttpAdapter):
    adapter_id = "finnhub"
    credential_mode = "query"
    credential_parameter = "token"


class FmpAdapter(ConfiguredHttpAdapter):
    adapter_id = "fmp"
    credential_mode = "query"
    credential_parameter = "apikey"


class AlphaVantageAdapter(ConfiguredHttpAdapter):
    adapter_id = "alpha_vantage"
    credential_mode = "query"
    credential_parameter = "apikey"


class AlphaVantageNewsAdapter(AlphaVantageAdapter):
    adapter_id = "alpha_vantage_news"


class GdeltAdapter(ConfiguredHttpAdapter):
    adapter_id = "gdelt"


class BrapiAdapter(ConfiguredHttpAdapter):
    adapter_id = "brapi"


class MarketstackAdapter(ConfiguredHttpAdapter):
    adapter_id = "marketstack"
    credential_mode = "query"
    credential_parameter = "access_key"


class MarketauxAdapter(ConfiguredHttpAdapter):
    adapter_id = "marketaux"
    credential_mode = "query"
    credential_parameter = "api_token"


class BeaAdapter(ConfiguredHttpAdapter):
    adapter_id = "bea"
    credential_mode = "query"
    credential_parameter = "UserID"


class BlsAdapter(ConfiguredHttpAdapter):
    adapter_id = "bls"
    default_method = "POST"
    allow_post = True

    def fetch_raw(self, task: dict, context: AdapterContext):
        spec = deepcopy(task.get("request_spec") or {})
        url = spec.get("url") or task.get("source_url")
        if not url:
            raise AdapterConfigurationError("bls requires request_spec.url")
        body = dict(spec.get("json") or {})
        series_ids = list(body.get("seriesid") or [])
        if not series_ids:
            return super().fetch_raw(task, context)
        handle = task.get("credential_handle")
        credential = context.credential_resolver.resolve(handle, required=False)
        start_year = int(body.get("startyear")) if body.get("startyear") else None
        end_year = int(body.get("endyear")) if body.get("endyear") else None
        year_windows = [(start_year, end_year)]
        if start_year is not None and end_year is not None and end_year - start_year + 1 > 20:
            year_windows = []
            cursor = start_year
            while cursor <= end_year:
                window_end = min(cursor + 19, end_year)
                year_windows.append((cursor, window_end))
                cursor = window_end + 1
        responses = []
        for i in range(0, len(series_ids), 50):
            batch = series_ids[i:i+50]
            for year_start, year_end in year_windows:
                payload = dict(body)
                payload["seriesid"] = batch
                if year_start is not None:
                    payload["startyear"] = str(year_start)
                if year_end is not None:
                    payload["endyear"] = str(year_end)
                if credential:
                    payload.setdefault("registrationkey", credential)
                responses.append(context.http_client.request(
                    "POST", url, params=dict(spec.get("params") or {}),
                    headers=dict(spec.get("headers") or {}), json_body=payload,
                ))
        return responses


class SecAdapter(ConfiguredHttpAdapter):
    adapter_id = "sec"

    def fetch_raw(self, task: dict, context: AdapterContext):
        spec = deepcopy(task.get("request_spec") or {})
        headers = dict(spec.get("headers") or {})
        handle = task.get("credential_handle")
        existing_user_agent = headers.get("User-Agent") or headers.get("user-agent")
        user_agent = existing_user_agent or context.credential_resolver.resolve(handle, required=not bool(existing_user_agent))
        if not user_agent:
            raise AdapterConfigurationError("sec requires an identifying User-Agent")
        headers.setdefault("User-Agent", user_agent)
        spec["headers"] = headers
        return super().fetch_raw({**task, "request_spec": spec, "credential_handle": None}, context)


class AlpacaAdapter(ConfiguredHttpAdapter):
    adapter_id = "alpaca"

    def fetch_raw(self, task: dict, context: AdapterContext):
        spec = deepcopy(task.get("request_spec") or {})
        headers = dict(spec.get("headers") or {})
        handles = task.get("credential_handles") or {}
        key = context.credential_resolver.resolve(handles.get("key_id"), required=bool(handles))
        secret = context.credential_resolver.resolve(handles.get("secret_key"), required=bool(handles))
        if key:
            headers.setdefault("APCA-API-KEY-ID", key)
        if secret:
            headers.setdefault("APCA-API-SECRET-KEY", secret)
        spec["headers"] = headers
        return super().fetch_raw({**task, "request_spec": spec, "credential_handle": None}, context)


class ExplicitAuthHttpAdapter(ConfiguredHttpAdapter):
    """For providers where auth transport must be declared, avoiding unsafe guesses."""

    def fetch_raw(self, task: dict, context: AdapterContext):
        spec = task.get("request_spec") or {}
        if task.get("credential_handle") and not spec.get("credential_mode"):
            raise AdapterConfigurationError(
                f"{self.adapter_id} requires explicit request_spec.credential_mode; auth transport is not guessed"
            )
        return super().fetch_raw(task, context)


class LseAdapter(ExplicitAuthHttpAdapter):
    adapter_id = "lse"


class B3Adapter(ConfiguredHttpAdapter):
    adapter_id = "b3"


class GenericHttpAdapter(ConfiguredHttpAdapter):
    adapter_id = "generic_http"


def _decode_json(content: bytes):
    try:
        return json.loads(content.decode("utf-8"))
    except Exception as exc:
        raise AdapterConfigurationError("pagination metadata response is not valid JSON") from exc
