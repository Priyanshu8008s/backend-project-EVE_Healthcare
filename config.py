"""
config.py — Centralised application settings via pydantic-settings.

All configuration is read from environment variables (with sane defaults
for local development).  A `.env` file is automatically loaded if present.

Usage anywhere in the app:
    from config import settings
    print(settings.DATABASE_URL)
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+psycopg2://eve_user:eve_password@localhost:5432/eve_diagnostic"
    )

    # ── JWT / Auth ────────────────────────────────────────────────────────
    SECRET_KEY: str = "YOUR_SECRET_KEY"          # Override in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Celery ───────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # ── Feature flags ─────────────────────────────────────────────────────
    # Set to False in test environments to skip async Celery dispatch and
    # keep the webhook endpoint synchronous (returns 200 instead of 202).
    CELERY_ENABLED: bool = True

    # pydantic-settings v2: load from .env file automatically
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Singleton — import this everywhere
settings = Settings()
