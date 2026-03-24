from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .secret_policy import validate_scope
from .secret_provider import EnvironmentSecretProvider, FileSecretProvider

GITHUB_TOKEN_ENV = "LUMENCORE_GITHUB_TOKEN"
BRAVE_API_KEY_ENV = "LUMENCORE_BRAVE_API_KEY"
TAVILY_API_KEY_ENV = "LUMENCORE_TAVILY_API_KEY"
EXA_API_KEY_ENV = "LUMENCORE_EXA_API_KEY"
OPENAI_API_KEY_ENV = "LUMENCORE_OPENAI_API_KEY"

SEARCH_PROVIDER_SECRET_ENV = {
    "brave": BRAVE_API_KEY_ENV,
    "tavily": TAVILY_API_KEY_ENV,
    "exa": EXA_API_KEY_ENV,
}

DEFAULT_SEARCH_PROVIDER_ORDER = ("brave", "tavily", "exa")


@dataclass(frozen=True)
class EnvSecretStatus:
    env_var: str
    configured: bool


class SecretManager:
    def __init__(
        self,
        provider: FileSecretProvider | None = None,
        env_provider: EnvironmentSecretProvider | None = None,
    ) -> None:
        self.provider = provider or FileSecretProvider()
        self.env_provider = env_provider or EnvironmentSecretProvider()

    def get_secret(self, scope: str, key: str, agent_id: str | None = None) -> str:
        safe_scope = validate_scope(scope)
        safe_key = (key or '').strip()
        if not safe_key:
            raise ValueError('secret key cannot be empty')

        if agent_id:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from ..db import SessionLocal
            from ..models import AgentSecretPermission

            session: Session | None = None
            try:
                session = SessionLocal()
                _ = session.execute(
                    select(AgentSecretPermission).where(
                        AgentSecretPermission.agent_id == agent_id,
                        AgentSecretPermission.secret_scope == safe_scope,
                        AgentSecretPermission.secret_key == safe_key,
                    )
                ).scalar_one_or_none()
            finally:
                if session is not None:
                    session.close()

        return self.provider.get(safe_scope, safe_key)

    def has_env_secret(self, env_var: str) -> bool:
        return self.env_provider.has(env_var)

    def get_env_secret(self, env_var: str) -> str:
        return self.env_provider.get(env_var)

    def describe_env_secret(self, env_var: str) -> EnvSecretStatus:
        return EnvSecretStatus(env_var=env_var, configured=self.has_env_secret(env_var))

    def resolve_env_secrets(self, env_vars: Sequence[str]) -> tuple[dict[str, str], list[str]]:
        resolved: dict[str, str] = {}
        missing: list[str] = []
        for env_var in env_vars:
            if self.has_env_secret(env_var):
                resolved[env_var] = self.get_env_secret(env_var)
            else:
                missing.append(env_var)
        return resolved, missing

    def available_search_providers(self) -> list[str]:
        return [provider for provider in DEFAULT_SEARCH_PROVIDER_ORDER if self.has_env_secret(SEARCH_PROVIDER_SECRET_ENV[provider])]

    def resolve_search_provider(self, requested_provider: str | None) -> str | None:
        normalized = str(requested_provider or "auto").strip().lower() or "auto"
        if normalized != "auto":
            return normalized

        available = self.available_search_providers()
        return available[0] if available else None

