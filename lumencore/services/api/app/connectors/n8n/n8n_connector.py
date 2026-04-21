"""n8n connector — allows Openclaw to manage and trigger n8n workflows."""
from __future__ import annotations

import os
import urllib.request
import urllib.error
import json

from ..base.connector import Connector

N8N_API_TOKEN_ENV = "N8N_API_TOKEN"
N8N_BASE_URL_ENV = "N8N_BASE_URL"
DEFAULT_N8N_URL = "http://localhost:5678"


class N8nConnector(Connector):
    connector_name = "n8n"
    connector_type = "automation"

    def supported_actions(self) -> tuple[str, ...]:
        return (
            "workflow.list",
            "workflow.get",
            "workflow.create",
            "workflow.activate",
            "workflow.deactivate",
            "workflow.execute",
            "execution.list",
            "execution.get",
        )

    def required_secret_names(self, payload, *, operation, provider, context=None):
        return (N8N_API_TOKEN_ENV,)

    def _get_credentials(self, context: dict | None) -> tuple[str, str]:
        secrets = (context or {}).get("resolved_secrets") or {}
        token = secrets.get(N8N_API_TOKEN_ENV) or os.environ.get(N8N_API_TOKEN_ENV, "")
        base_url = os.environ.get(N8N_BASE_URL_ENV, DEFAULT_N8N_URL).rstrip("/")
        return token, base_url

    def _request(self, method: str, path: str, token: str, base_url: str, body: dict | None = None) -> dict:
        url = f"{base_url}/api/v1{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-N8N-API-KEY": token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode()
            raise RuntimeError(f"n8n API error {exc.code}: {body_text}") from exc
        except Exception as exc:
            raise RuntimeError(f"n8n connection error: {exc}") from exc

    def execute(self, payload: dict, tenant_id: str, agent_id: str | None = None, context: dict | None = None):
        token, base_url = self._get_credentials(context)
        action = str(payload.get("action") or payload.get("operation") or "").strip()

        if action == "workflow.list":
            result = self._request("GET", "/workflows", token, base_url)
            return {"workflows": result.get("data", result)}

        if action == "workflow.get":
            wf_id = str(payload.get("workflow_id", ""))
            result = self._request("GET", f"/workflows/{wf_id}", token, base_url)
            return result

        if action == "workflow.create":
            wf_data = payload.get("workflow") or {}
            result = self._request("POST", "/workflows", token, base_url, wf_data)
            return result

        if action == "workflow.activate":
            wf_id = str(payload.get("workflow_id", ""))
            result = self._request("POST", f"/workflows/{wf_id}/activate", token, base_url)
            return result

        if action == "workflow.deactivate":
            wf_id = str(payload.get("workflow_id", ""))
            result = self._request("POST", f"/workflows/{wf_id}/deactivate", token, base_url)
            return result

        if action == "workflow.execute":
            wf_id = str(payload.get("workflow_id", ""))
            run_data = payload.get("data") or {}
            result = self._request("POST", f"/workflows/{wf_id}/run", token, base_url, {"data": run_data})
            return result

        if action == "execution.list":
            wf_id = payload.get("workflow_id")
            path = f"/executions?workflowId={wf_id}" if wf_id else "/executions"
            result = self._request("GET", path, token, base_url)
            return {"executions": result.get("data", result)}

        if action == "execution.get":
            exec_id = str(payload.get("execution_id", ""))
            result = self._request("GET", f"/executions/{exec_id}", token, base_url)
            return result

        raise ValueError(f"unsupported n8n action: {action}")
