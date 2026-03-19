from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..base.connector import Connector
from ...secrets.secret_manager import (
    BRAVE_API_KEY_ENV,
    EXA_API_KEY_ENV,
    TAVILY_API_KEY_ENV,
)


SUPPORTED_SEARCH_PROVIDERS = ("brave", "tavily", "exa")
DEFAULT_SEARCH_TIMEOUT_SECONDS = 8.0
DEFAULT_SEARCH_RESULT_LIMIT = 5
MAX_SEARCH_RESULT_LIMIT = 10


class SearchConnector(Connector):
    connector_name = "search"
    connector_type = "research"

    def supported_actions(self) -> tuple[str, ...]:
        return ("search.web_search",)

    def resolve_operation(self, payload: dict) -> str:
        operation = super().resolve_operation(payload)
        return operation or "search.web_search"

    def resolve_provider(self, payload: dict, context: dict | None = None) -> str | None:
        runtime = dict(context or {})
        requested = str((payload or {}).get("provider") or "auto").strip().lower() or "auto"
        secret_manager = runtime.get("secret_manager")
        if requested != "auto":
            return requested
        if secret_manager is None:
            return None
        return secret_manager.resolve_search_provider("auto")

    def provider_required(self, operation: str) -> bool:
        _ = operation
        return True

    def validate(self, payload: dict):
        query = str((payload or {}).get("query", "")).strip()
        return bool(query)

    def required_secret_names(self, payload: dict, *, operation: str, provider: str | None, context: dict | None = None) -> tuple[str, ...]:
        _ = payload, operation, context
        mapping = {
            "brave": BRAVE_API_KEY_ENV,
            "tavily": TAVILY_API_KEY_ENV,
            "exa": EXA_API_KEY_ENV,
        }
        if not provider:
            return ()
        secret_name = mapping.get(provider)
        return (secret_name,) if secret_name else ()

    def _request_json(self, request: Request, *, timeout_seconds: float) -> dict | list:
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise RuntimeError("provider_error:provider_access_denied") from exc
            raise RuntimeError(f"provider_error:http_{exc.code}") from exc
        except TimeoutError as exc:
            raise RuntimeError("timeout:provider_request_timed_out") from exc
        except URLError as exc:
            raise RuntimeError("provider_error:transport_error") from exc

    def _normalize_limit(self, payload: dict) -> int:
        try:
            requested = int((payload or {}).get("limit", DEFAULT_SEARCH_RESULT_LIMIT))
        except (TypeError, ValueError):
            requested = DEFAULT_SEARCH_RESULT_LIMIT
        return max(1, min(requested, MAX_SEARCH_RESULT_LIMIT))

    def _execute_brave(self, *, query: str, limit: int, api_key: str, timeout_seconds: float) -> list[dict]:
        url = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={limit}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            method="GET",
        )
        raw = self._request_json(request, timeout_seconds=timeout_seconds)
        results = []
        for item in ((raw.get("web") or {}).get("results") or [])[:limit]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("description"),
                    "provider": "brave",
                }
            )
        return results

    def _execute_tavily(self, *, query: str, limit: int, api_key: str, timeout_seconds: float) -> list[dict]:
        body = json.dumps({"query": query, "api_key": api_key, "max_results": limit}).encode("utf-8")
        request = Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        raw = self._request_json(request, timeout_seconds=timeout_seconds)
        results = []
        for item in (raw.get("results") or [])[:limit]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content"),
                    "provider": "tavily",
                }
            )
        return results

    def _execute_exa(self, *, query: str, limit: int, api_key: str, timeout_seconds: float) -> list[dict]:
        body = json.dumps({"query": query, "numResults": limit}).encode("utf-8")
        request = Request(
            "https://api.exa.ai/search",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": api_key,
            },
            method="POST",
        )
        raw = self._request_json(request, timeout_seconds=timeout_seconds)
        results = []
        for item in (raw.get("results") or [])[:limit]:
            results.append(
                {
                    "title": item.get("title") or item.get("text"),
                    "url": item.get("url"),
                    "snippet": item.get("text") or item.get("snippet"),
                    "provider": "exa",
                }
            )
        return results

    def execute(self, payload: dict, tenant_id: str, agent_id: str | None = None, context: dict | None = None):
        if not self.validate(payload):
            raise ValueError("query is required")

        runtime = dict(context or {})
        provider = str(runtime.get("provider") or self.resolve_provider(payload, context=runtime) or "").strip().lower()
        if provider not in SUPPORTED_SEARCH_PROVIDERS:
            raise ValueError("search provider is not configured")

        query = str(payload.get("query", "")).strip()
        limit = self._normalize_limit(payload)
        timeout_seconds = float(runtime.get("timeout_seconds") or DEFAULT_SEARCH_TIMEOUT_SECONDS)
        secrets = dict(runtime.get("resolved_secrets") or {})

        if provider == "brave":
            results = self._execute_brave(query=query, limit=limit, api_key=secrets[BRAVE_API_KEY_ENV], timeout_seconds=timeout_seconds)
        elif provider == "tavily":
            results = self._execute_tavily(query=query, limit=limit, api_key=secrets[TAVILY_API_KEY_ENV], timeout_seconds=timeout_seconds)
        else:
            results = self._execute_exa(query=query, limit=limit, api_key=secrets[EXA_API_KEY_ENV], timeout_seconds=timeout_seconds)

        return {
            "ok": True,
            "connector": self.connector_name,
            "operation": self.resolve_operation(payload),
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "provider": provider,
            "result": {
                "query": query,
                "limit": limit,
                "results": results,
            },
        }
