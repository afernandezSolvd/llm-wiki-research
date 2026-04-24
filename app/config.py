from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # DB
    database_url: str = "postgresql+asyncpg://llmwiki:llmwiki@localhost:5432/llmwiki"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"

    # Voyage (embeddings — separate service from Anthropic)
    voyage_api_key: str = ""
    anthropic_embedding_model: str = "voyage-3-large"

    # Storage
    storage_backend: str = "local"
    storage_local_root: str = "./data/sources"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = "llm-wiki-sources"
    aws_region: str = "us-east-1"

    # Wiki
    wiki_repos_root: str = "./wiki_repos"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Rate limiting
    rate_limit_default: int = 120
    rate_limit_ingest: int = 10
    rate_limit_query: int = 60
    rate_limit_lint: int = 5

    # Drift
    drift_alert_threshold: float = 0.35

    # Hallucination gate: verify LLM page edits against source before committing
    hallucination_gate_enabled: bool = True

    # KG
    kg_community_rebuild_debounce_minutes: int = 10

    # Hot pages cache
    hot_pages_cache_top_n: int = 10
    hot_pages_cache_ttl_seconds: int = 900

    # Public read-only portal API
    public_api_enabled: bool = True

    # Wiki git remote sync (Obsidian)
    wiki_git_enabled: bool = False
    wiki_git_provider: str = "github"
    wiki_git_provider_token: str = ""
    wiki_git_org: str = ""
    wiki_git_base_url: str = ""

    # App
    environment: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
