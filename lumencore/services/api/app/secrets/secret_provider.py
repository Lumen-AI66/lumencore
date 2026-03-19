from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

BASE_SECRETS_DIR = Path("/opt/lumencore/secrets")


class FileSecretProvider:
    def get(self, scope: str, key: str) -> str:
        path = BASE_SECRETS_DIR / scope / key
        if not path.exists() or not path.is_file():
            raise KeyError(f"secret not found: {scope}/{key}")
        return path.read_text(encoding="utf-8").strip()


class EnvironmentSecretProvider:
    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = dict(environ or os.environ)

    def has(self, key: str) -> bool:
        value = str(self._environ.get(key, "")).strip()
        return bool(value)

    def get(self, key: str) -> str:
        value = str(self._environ.get(key, "")).strip()
        if not value:
            raise KeyError(f"environment secret not found: {key}")
        return value
