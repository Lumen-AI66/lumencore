from __future__ import annotations

import os
from pathlib import Path

import yaml

from app.connectors.audit.connector_audit import get_connector_execution_summary, get_connector_metrics
from app.connectors.base.registry import get_registry
from app.connectors.connector_service import execute_connector_request
from app.connectors.policy.agent_connector_permissions import load_agent_connector_permissions
from app.connectors.policy.connector_policy import load_connector_enablement
from app.connectors.startup import register_default_connectors
from app.secrets.secret_manager import BRAVE_API_KEY_ENV, GITHUB_TOKEN_ENV


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = RUNTIME_ROOT / "config"
CONNECTOR_CONFIG_PATH = CONFIG_ROOT / "connectors.yaml"
LEGACY_CONNECTOR_SECRETS_PATH = RUNTIME_ROOT / "connectors" / "secrets.py"
DEFAULT_AGENT_ID = "11111111-1111-4111-8111-111111111111"


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    original_connector_config = _read_yaml(CONNECTOR_CONFIG_PATH)
    original_env = {GITHUB_TOKEN_ENV: os.environ.get(GITHUB_TOKEN_ENV), BRAVE_API_KEY_ENV: os.environ.get(BRAVE_API_KEY_ENV)}

    try:
        register_default_connectors(get_registry())
        _assert(not LEGACY_CONNECTOR_SECRETS_PATH.exists(), "parallel connector secrets layer should not remain")

        _assert(load_connector_enablement().get("git") is False, "git must remain disabled by default")
        _assert(load_connector_enablement().get("search") is False, "search must remain disabled by default")

        disabled_events: list[dict] = []
        disabled_result = execute_connector_request(
            connector_name="git",
            payload={"operation": "github.get_repo", "owner": "openai", "repo": "openai-python"},
            tenant_id="owner",
            agent_id=DEFAULT_AGENT_ID,
            audit_writer=disabled_events.append,
        )
        _assert(not disabled_result.allowed, "disabled connector should deny execution")
        _assert(any(event.get("metadata", {}).get("reason_code") == "connector_disabled" for event in disabled_events), "disabled connector denial should be observable")

        _write_yaml(
            CONNECTOR_CONFIG_PATH,
            {
                "CONNECTOR_ENABLEMENT": {"git": True, "search": True},
                "AGENT_CONNECTOR_PERMISSIONS": {
                    DEFAULT_AGENT_ID: {
                        "git": ["github.get_repo"],
                        "search": ["search.web_search"],
                    }
                },
            },
        )

        _assert(bool(load_agent_connector_permissions().get(DEFAULT_AGENT_ID, {}).get("git")), "permissions should load from connectors.yaml")

        missing_secret_events: list[dict] = []
        missing_secret_result = execute_connector_request(
            connector_name="git",
            payload={"operation": "github.get_repo", "owner": "openai", "repo": "openai-python"},
            tenant_id="owner",
            agent_id=DEFAULT_AGENT_ID,
            audit_writer=missing_secret_events.append,
        )
        _assert(not missing_secret_result.allowed, "missing secret should fail safely")
        _assert(any(event.get("metadata", {}).get("reason_code") == "missing_secret" for event in missing_secret_events), "missing secret should be observable")

        os.environ[GITHUB_TOKEN_ENV] = "github-test-token"
        os.environ[BRAVE_API_KEY_ENV] = "brave-test-key"

        registry = get_registry()
        git_connector = registry.get_connector("git")
        search_connector = registry.get_connector("search")

        git_connector._request_json = lambda url, token, timeout_seconds: {  # type: ignore[attr-defined]
            "full_name": "openai/openai-python",
            "description": "OpenAI Python SDK",
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/openai/openai-python",
        }
        search_connector._execute_brave = lambda query, limit, api_key, timeout_seconds: [  # type: ignore[attr-defined]
            {
                "title": "Brave Result",
                "url": "https://example.com/result",
                "snippet": "provider normalized",
                "provider": "brave",
            }
        ]

        git_success = execute_connector_request(
            connector_name="git",
            payload={"operation": "github.get_repo", "owner": "openai", "repo": "openai-python"},
            tenant_id="owner",
            agent_id=DEFAULT_AGENT_ID,
        )
        _assert(git_success.allowed, "git connector should execute once enabled, permitted, and configured")
        _assert((git_success.result or {}).get("provider") == "github", "git provider should be github")

        search_success = execute_connector_request(
            connector_name="search",
            payload={"operation": "search.web_search", "provider": "brave", "query": "lumencore", "limit": 3},
            tenant_id="owner",
            agent_id=DEFAULT_AGENT_ID,
        )
        _assert(search_success.allowed, "search connector should execute once enabled, permitted, and configured")
        _assert((search_success.result or {}).get("provider") == "brave", "search provider should be brave")

        summary = get_connector_execution_summary()
        totals = summary.get("totals", {})
        metrics = get_connector_metrics()
        _assert(int(metrics.get("connector_calls_total", 0)) >= 4, "connector calls should be counted")
        _assert(int(totals.get("connector_missing_secret_total", 0)) >= 1, "missing secrets should be counted")
        _assert(int(totals.get("connector_success_total", 0)) >= 2, "successful executions should be counted")
        _assert(summary.get("by_provider", {}).get("brave", 0) >= 1, "provider metrics should include brave")

        print("Phase 6 connector smoke checks passed")
    finally:
        _write_yaml(CONNECTOR_CONFIG_PATH, original_connector_config)
        for env_name, env_value in original_env.items():
            if env_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = env_value


if __name__ == "__main__":
    run()
