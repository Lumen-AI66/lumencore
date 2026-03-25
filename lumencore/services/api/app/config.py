import os
from pathlib import Path

import yaml


APP_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = APP_ROOT / "config"


def load_yaml_config(filename: str) -> dict:
    path = CONFIG_ROOT / filename
    if not path.exists():
        return {}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid YAML config: {filename}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"invalid YAML config shape: {filename}")
    return data


class Settings:
    app_env = os.getenv("APP_ENV", "production")
    api_port = int(os.getenv("API_PORT", "8000"))
    system_phase = os.getenv("LUMENCORE_SYSTEM_PHASE", "51")
    release_id = os.getenv("LUMENCORE_RELEASE_ID", "unversioned")
    release_manifest_sha256 = os.getenv("LUMENCORE_RELEASE_MANIFEST_SHA256", "")

    postgres_host = os.getenv("POSTGRES_HOST", "lumencore-postgres")
    postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db = os.getenv("POSTGRES_DB", "lumencore")
    postgres_user = os.getenv("POSTGRES_USER", "lumencore")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "")

    redis_host = os.getenv("REDIS_HOST", "lumencore-redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "")

    celery_broker_db = int(os.getenv("CELERY_BROKER_DB", "0"))
    celery_result_db = int(os.getenv("CELERY_RESULT_DB", "1"))

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.celery_broker_db}"

    @property
    def redis_result_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.celery_result_db}"


settings = Settings()












