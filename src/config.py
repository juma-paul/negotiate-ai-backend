"""Configuration and logging setup."""
import os
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App settings from environment."""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # Use mini for both (gpt-4o requires Tier 1+)
    openai_model_mini: str = "gpt-4o-mini"
    api_timeout: int = 30
    max_rounds: int = 5
    sse_heartbeat_interval: int = 15
    session_ttl_seconds: int = 3600
    allowed_origins: list[str] = ["https://frontend-ten-wine-44.vercel.app"]
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def setup_logging() -> logging.Logger:
    """Configure structured logging."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger("negotiate-ai")
    logger.setLevel(getattr(logging, settings.log_level))
    return logger


logger = setup_logging()
