from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..base.connector import Connector
from ...secrets.secret_manager import GITHUB_TOKEN_ENV


SAFE_GITHUB_OPERATIONS = {
    "github.get_repo",
    "github.list_pull_requests",
    "github.get_file",
}

DEFAULT_GITHUB_TIMEOUT_SECONDS = 8.0
DEFAULT_GITHUB_API_BASE = "https://api.github.com"


class GitConnector(Connector):
    connector_name = "git"
    connector_type = "scm"

    def supported_actions(self) -> tuple[str, ...]:
        return tuple(sorted(SAFE_GITHUB_OPERATIONS))

    def validate(self, payload: dict):
        operation = self.resolve_operation(payload)
        owner = str((payload or {}).get("owner", "")).strip()
        repo = str((payload or {}).get("repo", "")).strip()
        if operation not in SAFE_GITHUB_OPERATIONS or not owner or not repo:
            return False
        if operation == "github.get_file":
            return bool(str((payload or {}).get("path", "")).strip())
        return True

    def required_secret_names(self, payload: dict, *, operation: str, provider: str | None, context: dict | None = None) -> tuple[str, ...]:
        _ = payload, operation, provider, context
        return (GITHUB_TOKEN_ENV,)

    def _build_headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "lumencore-connector/phase6",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request_json(self, url: str, *, token: str, timeout_seconds: float) -> dict | list:
        request = Request(url, headers=self._build_headers(token), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise RuntimeError("provider_error:github_access_denied") from exc
            if exc.code == 404:
                raise RuntimeError("provider_error:github_resource_not_found") from exc
            raise RuntimeError(f"provider_error:github_http_{exc.code}") from exc
        except TimeoutError as exc:
            raise RuntimeError("timeout:github_request_timed_out") from exc
        except URLError as exc:
            raise RuntimeError("provider_error:github_transport_error") from exc

    def execute(self, payload: dict, tenant_id: str, agent_id: str | None = None, context: dict | None = None):
        if not self.validate(payload):
            raise ValueError("invalid git connector request")

        runtime = dict(context or {})
        secrets = dict(runtime.get("resolved_secrets") or {})
        token = str(secrets.get(GITHUB_TOKEN_ENV, "")).strip()
        if not token:
            raise ValueError("missing GitHub token")

        operation = self.resolve_operation(payload)
        owner = str(payload.get("owner", "")).strip()
        repo = str(payload.get("repo", "")).strip()
        timeout_seconds = float(runtime.get("timeout_seconds") or DEFAULT_GITHUB_TIMEOUT_SECONDS)
        api_base = str(runtime.get("api_base") or DEFAULT_GITHUB_API_BASE).rstrip("/")

        if operation == "github.get_repo":
            raw = self._request_json(f"{api_base}/repos/{quote(owner)}/{quote(repo)}", token=token, timeout_seconds=timeout_seconds)
            return {
                "ok": True,
                "connector": self.connector_name,
                "operation": operation,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "provider": "github",
                "result": {
                    "owner": owner,
                    "repo": repo,
                    "full_name": raw.get("full_name"),
                    "description": raw.get("description"),
                    "default_branch": raw.get("default_branch"),
                    "private": raw.get("private"),
                    "html_url": raw.get("html_url"),
                },
            }

        if operation == "github.list_pull_requests":
            state = str(payload.get("state", "open")).strip() or "open"
            raw = self._request_json(
                f"{api_base}/repos/{quote(owner)}/{quote(repo)}/pulls?state={quote(state)}",
                token=token,
                timeout_seconds=timeout_seconds,
            )
            items = []
            for item in list(raw)[:10]:
                items.append(
                    {
                        "number": item.get("number"),
                        "title": item.get("title"),
                        "state": item.get("state"),
                        "html_url": item.get("html_url"),
                        "user": (item.get("user") or {}).get("login"),
                    }
                )
            return {
                "ok": True,
                "connector": self.connector_name,
                "operation": operation,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "provider": "github",
                "result": {
                    "owner": owner,
                    "repo": repo,
                    "state": state,
                    "items": items,
                },
            }

        path = str(payload.get("path", "")).strip()
        raw = self._request_json(
            f"{api_base}/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path)}",
            token=token,
            timeout_seconds=timeout_seconds,
        )
        content = str(raw.get("content", "")).replace("\n", "")
        decoded = base64.b64decode(content).decode("utf-8", "ignore") if content else ""
        return {
            "ok": True,
            "connector": self.connector_name,
            "operation": operation,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "provider": "github",
            "result": {
                "owner": owner,
                "repo": repo,
                "path": path,
                "sha": raw.get("sha"),
                "encoding": raw.get("encoding"),
                "content": decoded,
            },
        }
