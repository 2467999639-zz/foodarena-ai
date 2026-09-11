"""Application settings loaded from environment variables."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .domain import ProviderMode

load_dotenv(override=False)


class Settings:
    """Runtime configuration for the FastAPI application."""

    def __init__(self) -> None:
        self.app_name = os.getenv("FOODARENA_APP_NAME", "FoodArena AI")
        self.database_url = os.getenv(
            "FOODARENA_DATABASE_URL", "sqlite:///./foodarena.db"
        )
        self.default_provider = ProviderMode(
            os.getenv("FOODARENA_PROVIDER", ProviderMode.MOCK.value)
        )
        static_env = os.getenv("FOODARENA_STATIC_DIR", "")
        self.static_dir: str | None = static_env if static_env else None


settings = Settings()
